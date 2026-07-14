from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.request_context import RequestContext, get_request_context  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.source import Source  # noqa: E402
from app.services.source_probe import SourceProbeEligibilityError, probe_source  # noqa: E402
from app.services.us_source_candidates import load_us_source_candidates  # noqa: E402


class _SingleResult:
    def __init__(self, row) -> None:
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _FakeSession:
    def __init__(self, row) -> None:
        self.row = row
        self.add_count = 0
        self.commit_count = 0

    def execute(self, _query):
        return _SingleResult(self.row)

    def add(self, _row) -> None:
        self.add_count += 1

    def commit(self) -> None:
        self.commit_count += 1


def _candidate_source(**overrides) -> Source:
    approved = load_us_source_candidates()[0]
    values = {
        "id": uuid.uuid4(),
        "org_id": uuid.uuid4(),
        "name": approved.name,
        "source_type": "automated",
        "adapter_key": approved.adapter_key,
        "url": approved.url,
        "collection_status": "candidate",
        "timeout_seconds": 37,
        "max_retries": 8,
        "is_active": False,
    }
    values.update(overrides)
    return Source(**values)


def _passing_frame(row_count: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Location": f"Test Elevator {index % 2}",
                "Name": "Corn" if index % 2 == 0 else "Soybeans",
                "Delivery": "07/01/2026",
                "Bushel Cash Price": 4.25 + index,
                "internal_token": "must-not-leak",
            }
            for index in range(row_count)
        ]
    )


class SourceProbeServiceTests(unittest.TestCase):
    def test_probe_returns_capped_sanitized_quality_summary_in_one_attempt(self) -> None:
        source = _candidate_source()
        with patch("app.services.source_probe.fetch_source_once", return_value=_passing_frame(12)) as fetch:
            result = probe_source(source)

        self.assertTrue(result["passed"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["timeout_seconds"], 37)
        self.assertEqual(result["raw_row_count"], 12)
        self.assertEqual(len(result["preview"]), 8)
        self.assertTrue(result["preview_truncated"])
        self.assertNotIn("internal_token", result["columns"])
        self.assertTrue(all("internal_token" not in row for row in result["preview"]))
        self.assertEqual(result["required_field_coverage"]["commodity"]["ratio"], 1.0)
        self.assertEqual(result["commodities"], ["Corn", "Soybeans"])
        self.assertFalse(result["persisted"])
        fetch.assert_called_once()

    def test_probe_returns_failed_reasons_for_incomplete_rows(self) -> None:
        source = _candidate_source()
        frame = pd.DataFrame(
            [
                {"Location": "A", "Name": "Corn", "Delivery": "July", "Basis": "-20"},
                {"Location": "", "Name": "", "Delivery": "", "Basis": ""},
            ]
        )
        with patch("app.services.source_probe.fetch_source_once", return_value=frame):
            result = probe_source(source)

        self.assertFalse(result["passed"])
        self.assertEqual(len(result["fail_reasons"]), 4)
        self.assertTrue(all("below 80%" in reason for reason in result["fail_reasons"]))

    def test_probe_rejects_unapproved_url_before_fetch(self) -> None:
        source = _candidate_source(url="https://example.com/not-approved")
        with patch("app.services.source_probe.fetch_source_once") as fetch:
            with self.assertRaisesRegex(SourceProbeEligibilityError, "approved US candidate config"):
                probe_source(source)
        fetch.assert_not_called()

    def test_probe_rejects_active_or_non_target_source(self) -> None:
        with self.assertRaisesRegex(SourceProbeEligibilityError, "inactive"):
            probe_source(_candidate_source(is_active=True))
        with self.assertRaisesRegex(SourceProbeEligibilityError, "target-aware"):
            probe_source(_candidate_source(adapter_key="agricharts"))


class SourceProbeApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_admin_probe_endpoint_does_not_write_or_change_source(self) -> None:
        source = _candidate_source()
        original_state = (source.collection_status, source.is_active)
        db = _FakeSession(source)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_context] = lambda: RequestContext(
            org_id=source.org_id,
            user_email="admin@example.com",
            user_role="admin",
        )

        with patch("app.services.source_probe.fetch_source_once", return_value=_passing_frame()):
            response = TestClient(app).post(f"/api/sources/{source.id}/probe")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["result"]["passed"])
        self.assertFalse(payload["result"]["persisted"])
        self.assertEqual((source.collection_status, source.is_active), original_state)
        self.assertEqual(db.add_count, 0)
        self.assertEqual(db.commit_count, 0)

    def test_probe_endpoint_is_admin_only(self) -> None:
        source = _candidate_source()
        db = _FakeSession(source)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_context] = lambda: RequestContext(
            org_id=source.org_id,
            user_email="member@example.com",
            user_role="member",
        )

        response = TestClient(app).post(f"/api/sources/{source.id}/probe")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin role required")


if __name__ == "__main__":
    unittest.main()
