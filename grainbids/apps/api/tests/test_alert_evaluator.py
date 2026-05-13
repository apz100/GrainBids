from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.alert_evaluator import (  # noqa: E402
    _compare,
    _extract_metric_value,
    _location_matches,
    _month_scope_matches,
    _saved_search_matches,
)


class AlertEvaluatorHelperTests(unittest.TestCase):
    def test_compare_operators(self) -> None:
        value = Decimal("1.50")
        self.assertTrue(_compare(value, Decimal("1.0"), ">"))
        self.assertTrue(_compare(value, Decimal("1.5"), ">="))
        self.assertTrue(_compare(value, Decimal("1.5"), "="))
        self.assertTrue(_compare(value, Decimal("2.0"), "<"))
        self.assertTrue(_compare(value, Decimal("1.5"), "<="))
        self.assertFalse(_compare(value, Decimal("2.0"), ">"))
        self.assertFalse(_compare(value, Decimal("1.0"), "<"))
        self.assertFalse(_compare(value, Decimal("1.5"), "!="))

    def test_location_match(self) -> None:
        self.assertTrue(_location_matches(None, "Cardinal Corn"))
        self.assertTrue(_location_matches("", "Cardinal Corn"))
        self.assertTrue(_location_matches("cardinal", "Cardinal Corn"))
        self.assertFalse(_location_matches("brinston", "Cardinal Corn"))
        self.assertFalse(_location_matches("brinston", None))

    def test_extract_metric_value(self) -> None:
        row = SimpleNamespace(
            basis=Decimal("1.0"),
            basis_change=Decimal("0.2"),
            cash_price_bu=Decimal("6.0"),
            cash_price_mt=Decimal("240.0"),
            cash_price_bu_change=Decimal("0.1"),
            cash_price_mt_change=Decimal("4.0"),
        )
        self.assertEqual(_extract_metric_value("basis", row), Decimal("1.0"))
        self.assertEqual(_extract_metric_value("basis_change", row), Decimal("0.2"))
        self.assertEqual(_extract_metric_value("cash_price_bu", row), Decimal("6.0"))
        self.assertEqual(_extract_metric_value("cash_price_mt", row), Decimal("240.0"))
        self.assertEqual(_extract_metric_value("cash_price_bu_change", row), Decimal("0.1"))
        self.assertEqual(_extract_metric_value("cash_price_mt_change", row), Decimal("4.0"))
        self.assertIsNone(_extract_metric_value("delivered_value", row))

    def test_extract_metric_value_ignores_nan(self) -> None:
        row = SimpleNamespace(
            basis=Decimal("NaN"),
            basis_change=None,
            cash_price_bu=None,
            cash_price_mt=None,
            cash_price_bu_change=None,
            cash_price_mt_change=None,
        )
        self.assertIsNone(_extract_metric_value("basis", row))

    def test_saved_search_match(self) -> None:
        saved_search = SimpleNamespace(
            filters_json={
                "location": "Brinston",
                "commodity_name": "Corn",
                "source_name": "Agricharts",
                "company_id": "11111111-1111-1111-1111-111111111111",
            }
        )
        matching_row = SimpleNamespace(
            location="Brinston Corn",
            commodity_name="Corn",
            source_name="Agricharts",
            company_id="11111111-1111-1111-1111-111111111111",
            location_id=None,
        )
        non_matching_row = SimpleNamespace(
            location="Hensall",
            commodity_name="Corn",
            source_name="Agricharts",
            company_id="11111111-1111-1111-1111-111111111111",
            location_id=None,
        )
        self.assertTrue(_saved_search_matches(saved_search, matching_row))
        self.assertFalse(_saved_search_matches(saved_search, non_matching_row))

    def test_month_scope_match(self) -> None:
        row = SimpleNamespace(
            delivery_label="May 26 Elev",
            delivery_end=None,
            delivery_start=None,
            futures_month="Jul 2026",
        )
        self.assertTrue(_month_scope_matches(["jul 2026"], row))
        self.assertTrue(_month_scope_matches(["may 26"], row))
        self.assertFalse(_month_scope_matches(["dec 2027"], row))


if __name__ == "__main__":
    unittest.main()
