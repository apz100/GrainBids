from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.platform.market_data.sources.orchestrator.GrainBidder import add_basis_change_column  # noqa: E402


class GrainBidderBasisChangeTests(unittest.TestCase):
    def test_matches_prior_with_renamed_headers(self) -> None:
        today = pd.DataFrame(
            [
                {
                    "Location": "Alliston Corn",
                    "Name": "Corn",
                    "Delivery": "May 2026",
                    "Delivery End": "May 2026",
                    "Futures Month": "July 2026",
                    "Basis": "140",
                }
            ]
        )
        prev = pd.DataFrame(
            [
                {
                    "Location": "Alliston Corn",
                    "Commodity": "Corn",
                    "Delivery Label": "May 2026",
                    "Delivery End": "May 2026",
                    "Symbol": "July 2026",
                    "Basis": "120",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            prev_path = Path(tmp) / "Ontario_CashBids_2026-05-27.csv"
            prev.to_csv(prev_path, index=False)
            out = add_basis_change_column(today, prev_path)

        self.assertIn("Basis Change", out.columns)
        self.assertEqual(float(out.iloc[0]["Basis Change"]), 20.0)

    def test_prefers_non_empty_duplicate_commodity_column(self) -> None:
        today = pd.DataFrame(
            [
                {
                    "Location": "Alliston Corn",
                    "Name": "Corn",
                    "Delivery": "May 2026",
                    "Delivery End": "May 2026",
                    "Futures Month": "July 2026",
                    "Basis": "140",
                }
            ]
        )
        prev_csv = "\n".join(
            [
                "Location,Commodity,Commodity,Delivery Label,Delivery End,Symbol,Basis",
                "Alliston Corn,,Corn,May 2026,May 2026,July 2026,130",
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            prev_path = Path(tmp) / "Ontario_CashBids_2026-05-27.csv"
            prev_path.write_text(prev_csv, encoding="utf-8")
            out = add_basis_change_column(today, prev_path)

        self.assertEqual(float(out.iloc[0]["Basis Change"]), 10.0)


if __name__ == "__main__":
    unittest.main()
