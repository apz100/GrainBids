from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.upload_csv import (  # noqa: E402
    _check_completeness,
    _extract_price_from_text,
    _infer_cash_price_mt,
    _parse_decimal,
    summarize_quality,
)


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

    def test_extract_price_from_text(self) -> None:
        value = _extract_price_from_text("ZCN26 @ 6.34")
        self.assertEqual(value, Decimal("6.34"))

    def test_infer_cash_price_mt_from_bushel(self) -> None:
        value = _infer_cash_price_mt(commodity_name="Corn", cash_price_bu=Decimal("6.16"))
        self.assertEqual(value, Decimal("242.51"))

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

    def test_quality_summary(self) -> None:
        summary = summarize_quality(
            raw_row_count=100,
            normalized_row_count=92,
            duplicate_key_count=3,
            rejected_row_count=8,
            missing_required_count=5,
            parse_success_rate=0.92,
            row_reject_reasons={"missing_basis": 4, "missing_cash_price_bu": 4},
        )
        self.assertEqual(summary["raw_row_count"], 100)
        self.assertEqual(summary["normalized_row_count"], 92)
        self.assertEqual(summary["rejected_row_count"], 8)
        self.assertEqual(summary["missing_required_count"], 5)
        self.assertEqual(summary["row_reject_reasons"], {"missing_basis": 4, "missing_cash_price_bu": 4})


if __name__ == "__main__":
    unittest.main()
