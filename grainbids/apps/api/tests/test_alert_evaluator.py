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


if __name__ == "__main__":
    unittest.main()
