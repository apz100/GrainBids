from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.ingestion import _reject_totals, _split_reject_breakdown  # noqa: E402


class IngestionQualityBreakdownTests(unittest.TestCase):
    def test_split_handles_nested_breakdown(self) -> None:
        payload = {
            "missing_basis": 4,
            "missing_cash_price_mt": 2,
            "_by_source": {
                "Agricharts": {"missing_basis": 3},
                "GLG": {"missing_basis": 1, "missing_cash_price_mt": 2},
            },
            "_by_field": {"basis": 4, "cash_price_mt": 2},
        }
        totals, by_source, by_field = _split_reject_breakdown(payload)
        self.assertEqual(totals["missing_basis"], 4)
        self.assertEqual(by_source["Agricharts"]["missing_basis"], 3)
        self.assertEqual(by_field["cash_price_mt"], 2)

    def test_reject_totals_falls_back_for_flat_payload(self) -> None:
        payload = {"missing_basis": 10, "missing_cash_price_bu": 2}
        totals = _reject_totals(payload)
        self.assertEqual(totals, payload)


if __name__ == "__main__":
    unittest.main()

