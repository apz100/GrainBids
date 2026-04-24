from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.upload_csv import _check_completeness, _parse_decimal  # noqa: E402


class UploadQualityTests(unittest.TestCase):
    def test_parse_decimal_handles_tick_quotes(self) -> None:
        value = _parse_decimal("456'6")
        self.assertIsNotNone(value)
        self.assertEqual(str(value), "456.75")

    def test_parse_decimal_handles_tick_hyphen(self) -> None:
        value = _parse_decimal("456-6")
        self.assertIsNotNone(value)
        self.assertEqual(str(value), "456.75")

    def test_parse_decimal_rejects_nan(self) -> None:
        self.assertIsNone(_parse_decimal("NaN"))

    def test_completeness_requires_delivery_window(self) -> None:
        reasons = _check_completeness(
            source_name="Andersons",
            delivery_end="",
            delivery_label="",
            futures_month="May 2026",
            basis=Decimal("0.12"),
            cash_price_bu=Decimal("6.10"),
            cash_price_mt=Decimal("240.20"),
        )
        self.assertIn("missing_delivery_window", reasons)

    def test_completeness_detects_missing_prices(self) -> None:
        reasons = _check_completeness(
            source_name="GLG",
            delivery_end="2026-04-30",
            delivery_label="Apr 30",
            futures_month="Jul 2026",
            basis=None,
            cash_price_bu=None,
            cash_price_mt=Decimal("250.00"),
        )
        self.assertIn("missing_basis", reasons)
        self.assertIn("missing_cash_price_bu", reasons)
        self.assertNotIn("missing_cash_price_mt", reasons)

    def test_completeness_passes_with_required_values(self) -> None:
        reasons = _check_completeness(
            source_name="Bunge",
            delivery_end="2026-05-31",
            delivery_label="May",
            futures_month="Jul 2026",
            basis=Decimal("0.15"),
            cash_price_bu=Decimal("6.25"),
            cash_price_mt=Decimal("246.00"),
        )
        self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()
