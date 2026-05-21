from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.upload_csv import (  # noqa: E402
    _choose_company_id_for_row,
    _check_completeness,
    _derive_delivery_month_from_futures_month,
    _extract_price_from_text,
    _is_invalid_commodity_name,
    _parse_decimal,
    _source_creates_company_identity,
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

    def test_derive_delivery_month_from_futures_month_abbrev(self) -> None:
        self.assertEqual(_derive_delivery_month_from_futures_month("Jul 2026"), "June 2026")

    def test_derive_delivery_month_from_futures_month_rollover(self) -> None:
        self.assertEqual(_derive_delivery_month_from_futures_month("Jan 2027"), "December 2026")

    def test_invalid_commodity_name_rejects_source_labels(self) -> None:
        self.assertTrue(_is_invalid_commodity_name("Mixed Daily File", "Ganaraska"))
        self.assertTrue(_is_invalid_commodity_name("Eastern Ontario Cash Bids", "Eastern Ontario Cash Bids"))
        self.assertFalse(_is_invalid_commodity_name("Corn", "Ganaraska"))

    def test_completeness_requires_delivery_window(self) -> None:
        reasons = _check_completeness(
            source_name="Andersons",
            delivery_end="",
            delivery_label="",
            futures_month="May 2026",
            futures_month_raw="ZCK26",
            futures_change=Decimal("0.05"),
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
            futures_month_raw="ZCN26",
            futures_change=Decimal("0.03"),
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
            futures_month_raw="ZCN26",
            futures_change=Decimal("0.02"),
            basis=Decimal("0.15"),
            cash_price_bu=Decimal("6.25"),
            cash_price_mt=Decimal("246.00"),
        )
        self.assertEqual(reasons, [])

    def test_snobelen_requires_futures_change_and_source_month(self) -> None:
        reasons = _check_completeness(
            source_name="Snobelen",
            delivery_end="2026-05-31",
            delivery_label="May",
            futures_month="Jul 2026",
            futures_month_raw="",
            futures_change=None,
            basis=Decimal("0.15"),
            cash_price_bu=Decimal("6.25"),
            cash_price_mt=Decimal("246.00"),
        )
        self.assertIn("missing_futures_change", reasons)
        self.assertIn("missing_futures_month_source", reasons)

    def test_ganaraska_requires_futures_change(self) -> None:
        reasons = _check_completeness(
            source_name="Ganaraska",
            delivery_end="2026-05-31",
            delivery_label="May",
            futures_month="Jul 2026",
            futures_month_raw="ZCN26",
            futures_change=None,
            basis=Decimal("0.15"),
            cash_price_bu=Decimal("6.25"),
            cash_price_mt=Decimal("246.00"),
        )
        self.assertIn("missing_futures_change", reasons)

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

    def test_aggregator_source_does_not_create_company_identity(self) -> None:
        self.assertFalse(_source_creates_company_identity("Agricharts"))
        self.assertTrue(_source_creates_company_identity("GLG"))
        self.assertFalse(_source_creates_company_identity("Ontario Cash Bids"))

    def test_choose_company_id_for_row_prefers_location_company_for_aggregator(self) -> None:
        location_company_id = uuid.uuid4()
        self.assertEqual(
            _choose_company_id_for_row(
                source_name="Agricharts",
                explicit_company_id=None,
                location_company_id=location_company_id,
            ),
            location_company_id,
        )

    def test_choose_company_id_for_row_keeps_explicit_company_for_company_site(self) -> None:
        explicit_company_id = uuid.uuid4()
        location_company_id = uuid.uuid4()
        self.assertEqual(
            _choose_company_id_for_row(
                source_name="GLG",
                explicit_company_id=explicit_company_id,
                location_company_id=location_company_id,
            ),
            explicit_company_id,
        )


if __name__ == "__main__":
    unittest.main()
