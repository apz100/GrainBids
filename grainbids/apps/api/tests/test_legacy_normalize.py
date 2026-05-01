from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.imports.legacy_normalize import normalize_legacy_dataframe  # noqa: E402


class LegacyNormalizeTests(unittest.TestCase):
    def test_normalize_accepts_punctuated_futures_price_header(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "Location Name": "Cardinal",
                    "Commodity": "Corn",
                    "Delivery Label": "May",
                    "Futures Symbol": "ZCN26",
                    "Futures ($/bu)": "6.34",
                    "Basis": "0.12",
                    "Cash Price (tonne)": "248.10",
                    "Bushel Cash Price": "6.46",
                }
            ]
        )

        normalized = normalize_legacy_dataframe(df)
        self.assertEqual(str(normalized.iloc[0]["location"]), "Cardinal")
        self.assertEqual(str(normalized.iloc[0]["commodity"]), "Corn")
        self.assertEqual(str(normalized.iloc[0]["futures_month"]), "July 2026")
        self.assertEqual(str(normalized.iloc[0]["futures_price"]), "6.34")


if __name__ == "__main__":
    unittest.main()
