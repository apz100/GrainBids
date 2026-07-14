from __future__ import annotations

import sys
import unittest
from pathlib import Path
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.us_source_candidates import load_us_source_candidates, seed_us_source_candidates  # noqa: E402


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, existing=None) -> None:
        self.existing = existing or []
        self.added = []
        self.commit_count = 0

    def execute(self, _query):
        return _RowsResult(self.existing)

    def add(self, row) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commit_count += 1


class USSourceCandidateTests(unittest.TestCase):
    def test_config_loader_returns_only_enabled_supported_unique_sources(self) -> None:
        rows = load_us_source_candidates()

        self.assertGreaterEqual(len(rows), 20)
        self.assertEqual(len({row.url for row in rows}), len(rows))
        self.assertEqual(len({row.name.casefold() for row in rows}), len(rows))
        self.assertTrue({row.adapter_key for row in rows}.issubset({"us_agricharts", "us_dtn"}))
        self.assertNotIn("unknown", {row.adapter_key for row in rows})

    def test_seed_creates_inactive_candidates_without_fetching(self) -> None:
        db = _FakeSession()
        result = seed_us_source_candidates(db, org_id=uuid.uuid4())

        self.assertEqual(result["created"], len(db.added))
        self.assertGreater(result["created"], 0)
        self.assertEqual(db.commit_count, 1)
        self.assertTrue(all(row.collection_status == "candidate" for row in db.added))
        self.assertTrue(all(row.is_active is False for row in db.added))
        self.assertTrue(all(row.country_code == "US" for row in db.added))
        self.assertTrue(all(row.currency_code == "USD" for row in db.added))

    def test_seed_is_idempotent_by_url(self) -> None:
        existing = [
            type("ExistingSource", (), {"url": row.url, "name": row.name})()
            for row in load_us_source_candidates()
        ]
        db = _FakeSession(existing=existing)
        result = seed_us_source_candidates(db, org_id=uuid.uuid4())

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["skipped"], len(existing))
        self.assertEqual(db.added, [])
        self.assertEqual(db.commit_count, 0)


if __name__ == "__main__":
    unittest.main()
