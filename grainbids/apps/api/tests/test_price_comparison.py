from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.price_comparison import (  # noqa: E402
    build_composite_key,
    calculate_basis_change_policy,
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

    def test_basis_change_policy_uses_run_delta_when_basis_changes(self) -> None:
        captured_at = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
        policy = calculate_basis_change_policy(
            basis=Decimal("2.30"),
            captured_at=captured_at,
            prior_day_basis=Decimal("2.07"),
            prior_run_basis=Decimal("2.29"),
            prior_user_basis_change=Decimal("0.01"),
            prior_basis_last_changed_at=datetime(2026, 5, 28, 20, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(policy.basis_change_strict, Decimal("0.23"))
        self.assertEqual(policy.basis_change, Decimal("0.01"))
        self.assertEqual(policy.basis_last_changed_at, captured_at)

    def test_basis_change_policy_carries_last_move_within_24h(self) -> None:
        captured_at = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
        changed_at = captured_at - timedelta(hours=14)
        policy = calculate_basis_change_policy(
            basis=Decimal("2.30"),
            captured_at=captured_at,
            prior_day_basis=Decimal("2.07"),
            prior_run_basis=Decimal("2.30"),
            prior_user_basis_change=Decimal("0.23"),
            prior_basis_last_changed_at=changed_at,
        )
        self.assertEqual(policy.basis_change_strict, Decimal("0.23"))
        self.assertEqual(policy.basis_change, Decimal("0.23"))
        self.assertEqual(policy.basis_last_changed_at, changed_at)

    def test_basis_change_policy_expires_carry_after_24h(self) -> None:
        captured_at = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
        changed_at = captured_at - timedelta(hours=26)
        policy = calculate_basis_change_policy(
            basis=Decimal("2.30"),
            captured_at=captured_at,
            prior_day_basis=Decimal("2.07"),
            prior_run_basis=Decimal("2.30"),
            prior_user_basis_change=Decimal("0.23"),
            prior_basis_last_changed_at=changed_at,
        )
        self.assertEqual(policy.basis_change_strict, Decimal("0.23"))
        self.assertEqual(policy.basis_change, Decimal("0.0"))
        self.assertIsNone(policy.basis_last_changed_at)

    def test_basis_change_policy_defaults_to_zero_when_no_prior_run(self) -> None:
        captured_at = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
        policy = calculate_basis_change_policy(
            basis=Decimal("2.30"),
            captured_at=captured_at,
            prior_day_basis=None,
            prior_run_basis=None,
            prior_user_basis_change=None,
            prior_basis_last_changed_at=None,
        )
        self.assertIsNone(policy.basis_change_strict)
        self.assertEqual(policy.basis_change, Decimal("0.0"))
        self.assertIsNone(policy.basis_last_changed_at)

    def test_basis_change_policy_multi_snapshot_carry_then_reset(self) -> None:
        day1_pm = datetime(2026, 5, 28, 20, 0, tzinfo=timezone.utc)
        day2_am = datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc)
        day3_pm = datetime(2026, 5, 30, 22, 30, tzinfo=timezone.utc)

        moved = calculate_basis_change_policy(
            basis=Decimal("2.30"),
            captured_at=day1_pm,
            prior_day_basis=Decimal("2.07"),
            prior_run_basis=Decimal("2.07"),
            prior_user_basis_change=Decimal("0.00"),
            prior_basis_last_changed_at=day1_pm - timedelta(hours=12),
        )
        self.assertEqual(moved.basis_change, Decimal("0.23"))
        self.assertEqual(moved.basis_last_changed_at, day1_pm)

        carried = calculate_basis_change_policy(
            basis=Decimal("2.30"),
            captured_at=day2_am,
            prior_day_basis=Decimal("2.07"),
            prior_run_basis=Decimal("2.30"),
            prior_user_basis_change=moved.basis_change,
            prior_basis_last_changed_at=moved.basis_last_changed_at,
        )
        self.assertEqual(carried.basis_change, Decimal("0.23"))
        self.assertEqual(carried.basis_last_changed_at, day1_pm)

        expired = calculate_basis_change_policy(
            basis=Decimal("2.30"),
            captured_at=day3_pm,
            prior_day_basis=Decimal("2.30"),
            prior_run_basis=Decimal("2.30"),
            prior_user_basis_change=carried.basis_change,
            prior_basis_last_changed_at=carried.basis_last_changed_at,
        )
        self.assertEqual(expired.basis_change, Decimal("0.0"))
        self.assertIsNone(expired.basis_last_changed_at)


if __name__ == "__main__":
    unittest.main()
