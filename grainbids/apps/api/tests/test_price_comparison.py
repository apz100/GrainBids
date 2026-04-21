from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.price_comparison import (  # noqa: E402
    build_composite_key,
    calculate_price_changes,
    select_most_recent_prior,
)


@dataclass(frozen=True)
class Candidate:
    name: str


class PriceComparisonTests(unittest.TestCase):
    def test_no_prior_match_returns_null_changes(self) -> None:
        changes = calculate_price_changes(
            basis=Decimal("0.25"),
            cash_price_bu=Decimal("4.75"),
            cash_price_mt=Decimal("187.00"),
            prior_basis=None,
            prior_cash_price_bu=None,
            prior_cash_price_mt=None,
        )

        self.assertIsNone(changes.basis_change)
        self.assertIsNone(changes.cash_price_bu_change)
        self.assertIsNone(changes.cash_price_mt_change)

    def test_changed_futures_month_changes_matching_key(self) -> None:
        old_key = build_composite_key(
            location="London",
            commodity_name="Corn",
            delivery_start="2026-04-01",
            delivery_end="2026-04-30",
            futures_month="May 2026",
        )
        new_key = build_composite_key(
            location="London",
            commodity_name="Corn",
            delivery_start="2026-04-01",
            delivery_end="2026-04-30",
            futures_month="Jul 2026",
        )

        self.assertNotEqual(old_key, new_key)

    def test_duplicate_composite_key_uses_most_recent_prior(self) -> None:
        older = Candidate("older")
        newer = Candidate("newer")
        selected = select_most_recent_prior(
            [
                (older, datetime(2026, 4, 1, tzinfo=timezone.utc)),
                (newer, datetime(2026, 4, 20, tzinfo=timezone.utc)),
            ]
        )

        self.assertEqual(selected, newer)

    def test_blank_or_null_basis_returns_null_basis_change(self) -> None:
        changes = calculate_price_changes(
            basis=None,
            cash_price_bu=Decimal("5.10"),
            cash_price_mt=None,
            prior_basis=Decimal("0.15"),
            prior_cash_price_bu=Decimal("5.00"),
            prior_cash_price_mt=Decimal("190.00"),
        )

        self.assertIsNone(changes.basis_change)
        self.assertEqual(changes.cash_price_bu_change, Decimal("0.10"))
        self.assertIsNone(changes.cash_price_mt_change)


if __name__ == "__main__":
    unittest.main()
