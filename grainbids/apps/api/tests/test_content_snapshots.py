from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
import uuid

from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.execute_count = 0

    def execute(self, _query):
        self.execute_count += 1
        return _FakeResult(self.rows)


class ContentSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = {
            "content_snapshot_api_keys": settings.content_snapshot_api_keys,
            "content_snapshot_org_id": settings.content_snapshot_org_id,
            "content_snapshot_currency_code": settings.content_snapshot_currency_code,
            "content_snapshot_max_age_minutes": settings.content_snapshot_max_age_minutes,
        }
        app.dependency_overrides.clear()

    def tearDown(self) -> None:
        for name, value in self.original.items():
            setattr(settings, name, value)
        app.dependency_overrides.clear()

    def _configure(self, *, max_age_minutes: int = 1440) -> uuid.UUID:
        org_id = uuid.uuid4()
        settings.content_snapshot_api_keys = "old-key-abcdefghijklmnopqrstuvwxyz,new-key-abcdefghijklmnopqrstuvwxyz"
        settings.content_snapshot_org_id = str(org_id)
        settings.content_snapshot_currency_code = "CAD"
        settings.content_snapshot_max_age_minutes = max_age_minutes
        return org_id

    def _row(self, *, captured_at: datetime | None = None):
        captured_at = captured_at or datetime.now(timezone.utc) - timedelta(minutes=5)
        company_id = uuid.uuid4()
        location_id = uuid.uuid4()
        source_id = uuid.uuid4()
        snapshot_id = uuid.uuid4()
        price = SimpleNamespace(
            id=uuid.uuid4(),
            snapshot_id=snapshot_id,
            company_id=company_id,
            location_id=location_id,
            location="Chesterville",
            commodity_name="Corn",
            source_name="Great Lakes Grain",
            delivery_label="September 2026",
            delivery_start="2026-09-01",
            delivery_end="2026-09-30",
            futures_month="December 2026",
            futures_price=Decimal("4.25"),
            futures_change=Decimal("0.05"),
            basis=Decimal("125"),
            basis_change=Decimal("5"),
            basis_change_strict=Decimal("4"),
            cash_price_bu=Decimal("5.50"),
            cash_price_mt=Decimal("216.52"),
            cash_price_bu_change=Decimal("0.09"),
            cash_price_mt_change=Decimal("3.54"),
            is_canonical=True,
            canonical_rank=1,
            canonical_reason="preferred source",
        )
        snapshot = SimpleNamespace(id=snapshot_id, captured_at=captured_at)
        source = SimpleNamespace(
            id=source_id,
            name="GLG",
            url="https://example.test/bids",
            source_type="automated",
            region="Ontario",
            confidence_score=Decimal("0.975"),
            last_success_at=captured_at,
            consecutive_failures=0,
        )
        company = SimpleNamespace(id=company_id, name="Great Lakes Grain")
        location = SimpleNamespace(
            id=location_id,
            name="Chesterville",
            region="Eastern Ontario",
            postal_code="K0C 1H0",
            latitude=Decimal("45.100000"),
            longitude=Decimal("-75.200000"),
        )
        return price, snapshot, source, company, location

    def _override_db(self, db) -> None:
        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db

    def test_interface_is_disabled_until_server_configuration_exists(self) -> None:
        settings.content_snapshot_api_keys = ""
        settings.content_snapshot_org_id = ""
        self._override_db(_FakeSession([]))

        response = TestClient(app).get("/api/content/v1/snapshots/cash-bids")

        self.assertEqual(response.status_code, 503)

    def test_bearer_token_is_required_and_checked(self) -> None:
        self._configure()
        self._override_db(_FakeSession([]))
        client = TestClient(app)

        missing = client.get("/api/content/v1/snapshots/cash-bids")
        invalid = client.get(
            "/api/content/v1/snapshots/cash-bids",
            headers={"Authorization": "Bearer wrong-key"},
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(missing.headers.get("www-authenticate"), "Bearer")

    def test_snapshot_returns_versioned_canonical_rows_with_lineage_and_units(self) -> None:
        self._configure()
        db = _FakeSession([self._row()])
        self._override_db(db)

        response = TestClient(app).get(
            "/api/content/v1/snapshots/cash-bids?region=Ontario&commodity=Corn&commodity=Wheat",
            headers={"Authorization": "Bearer new-key-abcdefghijklmnopqrstuvwxyz"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "grainbids.content-snapshot.v1")
        self.assertTrue(payload["snapshot_id"].startswith("sha256:"))
        self.assertEqual(payload["row_count"], 1)
        self.assertFalse(payload["truncated"])
        self.assertEqual(payload["freshness"]["status"], "fresh")
        self.assertEqual(payload["filters"]["commodities"], ["Corn", "Wheat"])
        row = payload["rows"][0]
        self.assertEqual(row["company_name"], "Great Lakes Grain")
        self.assertEqual(row["facility_name"], "Chesterville")
        self.assertEqual(row["basis"], 1.25)
        self.assertEqual(row["cash_price_bu_unit"], "CAD/bu")
        self.assertEqual(row["cash_price_mt_unit"], "CAD/MT")
        self.assertEqual(row["source_name"], "GLG")
        self.assertNotIn("email", row)
        self.assertNotIn("subscriber", payload)
        self.assertEqual(db.execute_count, 1)

    def test_snapshot_reports_stale_and_truncated_data_without_silently_publishing_it(self) -> None:
        self._configure(max_age_minutes=60)
        old_capture = datetime.now(timezone.utc) - timedelta(days=2)
        db = _FakeSession([self._row(captured_at=old_capture), self._row(captured_at=old_capture)])
        self._override_db(db)

        response = TestClient(app).get(
            "/api/content/v1/snapshots/cash-bids?limit=1",
            headers={"Authorization": "Bearer old-key-abcdefghijklmnopqrstuvwxyz"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["freshness"]["status"], "stale")
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["row_count"], 1)


if __name__ == "__main__":
    unittest.main()
