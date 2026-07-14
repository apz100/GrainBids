from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_orchestration import _promotion_status, list_due_sources  # noqa: E402


class _EmptyRowsResult:
    def scalars(self):
        return self

    def all(self):
        return []


class _CaptureSession:
    def __init__(self) -> None:
        self.query = None

    def execute(self, query):
        self.query = query
        return _EmptyRowsResult()


def _source(**overrides):
    values = {
        "source_type": "automated",
        "collection_status": "candidate",
        "confidence_score": None,
        "consecutive_failures": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SourceCollectionControlTests(unittest.TestCase):
    def test_candidate_and_quarantined_sources_are_not_promoted(self) -> None:
        self.assertEqual(_promotion_status(source=_source(), successful_run_count=10), "candidate")
        self.assertEqual(
            _promotion_status(
                source=_source(collection_status="quarantined", confidence_score=1),
                successful_run_count=10,
            ),
            "quarantined",
        )

    def test_pilot_requires_quality_history_before_active_readiness(self) -> None:
        pilot = _source(collection_status="pilot", confidence_score=0.8)
        self.assertEqual(_promotion_status(source=pilot, successful_run_count=2), "pilot")
        self.assertEqual(_promotion_status(source=pilot, successful_run_count=3), "ready_for_active")

    def test_due_source_query_requires_collection_status_and_supported_adapter(self) -> None:
        db = _CaptureSession()
        self.assertEqual(list_due_sources(db), [])

        query_text = str(db.query)
        params = db.query.compile().params
        self.assertIn("sources.collection_status IN", query_text)
        self.assertIn("sources.adapter_key IN", query_text)
        self.assertEqual(set(params["collection_status_1"]), {"pilot", "active"})
        self.assertIn("us_agricharts", params["adapter_key_1"])
        self.assertIn("us_dtn", params["adapter_key_1"])


if __name__ == "__main__":
    unittest.main()
