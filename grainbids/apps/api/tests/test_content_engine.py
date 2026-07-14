from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.content_engine import (  # noqa: E402
    ALLOWED_STATUSES,
    build_content_bundle,
    generate_content_draft,
    get_region_config,
)


NOW = datetime(2026, 7, 14, 20, 0, tzinfo=timezone.utc)
REGION = get_region_config("eastern_ontario")


def _row(
    *,
    row_id: str,
    source_id: str,
    location: str,
    cash_bu: float | None = 5.25,
    cash_mt: float | None = 206.68,
    currency: str = "CAD",
    commodity: str = "Corn",
    delivery: str | None = "October 2026",
    futures: str | None = "December 2026",
    captured_at: datetime = NOW - timedelta(hours=1),
    strict_change: float | None = None,
    **extra,
) -> dict[str, object]:
    return {
        "id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "source_id": source_id,
        "source_name": f"Source {source_id}",
        "source_active": True,
        "source_collection_status": "active",
        "currency": currency,
        "captured_at": captured_at,
        "commodity": commodity,
        "location": location,
        "buyer_name": f"Buyer {source_id}",
        "delivery_label": delivery,
        "futures_month": futures,
        "basis_change_strict": strict_change,
        "cash_price_bu": cash_bu,
        "cash_price_mt": cash_mt,
        "is_canonical": True,
        **extra,
    }


def _healthy_rows() -> list[dict[str, object]]:
    return [
        _row(row_id="row-1", source_id="source-1", location="Chesterville", cash_bu=5.20),
        _row(row_id="row-2", source_id="source-2", location="Johnstown", cash_bu=5.45),
    ]


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DraftSession:
    def __init__(self) -> None:
        self.saved = None
        self.add_count = 0
        self.commit_count = 0

    def execute(self, _query):
        return _ScalarResult(self.saved)

    def add(self, row):
        self.saved = row
        self.add_count += 1

    def commit(self):
        self.commit_count += 1

    def refresh(self, row):
        if row.id is None:
            row.id = uuid.uuid4()


class ContentEngineTests(unittest.TestCase):
    def test_daily_and_weekly_draft_bundles_are_produced(self) -> None:
        daily = build_content_bundle(_healthy_rows(), cadence="daily", region=REGION, generated_at=NOW)
        weekly = build_content_bundle(_healthy_rows(), cadence="weekly", region=REGION, generated_at=NOW)

        self.assertEqual(daily.status, "draft")
        self.assertEqual(weekly.status, "draft")
        self.assertIn(":daily:2026-07-14", daily.issue_key)
        self.assertIn(":weekly:2026-W29", weekly.issue_key)
        self.assertIn("POSTED BIDS", daily.artifacts["email"]["text"])
        self.assertTrue(weekly.artifacts["social"])
        self.assertTrue(weekly.artifacts["site"]["tables"])

    def test_unrelated_delivery_periods_are_never_ranked_together(self) -> None:
        rows = [
            _row(
                row_id="nearby",
                source_id="source-1",
                location="Chesterville",
                cash_bu=5.10,
                cash_mt=None,
                delivery="July 2026",
            ),
            _row(
                row_id="harvest",
                source_id="source-2",
                location="Johnstown",
                cash_bu=6.50,
                cash_mt=None,
                delivery="October 2026",
            ),
        ]

        bundle = build_content_bundle(rows, cadence="daily", region=REGION, generated_at=NOW)
        cash_facts = [fact for fact in bundle.facts["facts"] if fact["fact_type"] == "posted_bid_summary"]

        self.assertEqual(len(cash_facts), 2)
        self.assertEqual({fact["count"] for fact in cash_facts}, {1})
        self.assertFalse(any(fact["low"] == 5.10 and fact["high"] == 6.50 for fact in cash_facts))

    def test_strict_basis_change_requires_exact_delivery_and_futures_metadata(self) -> None:
        exact = _row(
            row_id="exact",
            source_id="source-1",
            location="Chesterville",
            strict_change=0.12,
            strict_prior_row_id="prior-exact",
            strict_prior_delivery_label="October 2026",
            strict_prior_futures_month="December 2026",
        )
        wrong_delivery = _row(
            row_id="wrong-delivery",
            source_id="source-2",
            location="Johnstown",
            strict_change=0.40,
            strict_prior_delivery_label="November 2026",
            strict_prior_futures_month="December 2026",
        )
        wrong_futures = _row(
            row_id="wrong-futures",
            source_id="source-3",
            location="Prescott",
            strict_change=0.55,
            strict_prior_delivery_label="October 2026",
            strict_prior_futures_month="March 2027",
        )

        bundle = build_content_bundle(
            [exact, wrong_delivery, wrong_futures], cadence="daily", region=REGION, generated_at=NOW
        )
        changes = [fact for fact in bundle.facts["facts"] if fact["fact_type"] == "strict_basis_change"]

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["value"], 0.12)
        self.assertEqual(changes[0]["source_row_ids"], ["exact", "prior-exact"])
        self.assertIn("December 2026", changes[0]["comparison_key"])

    def test_currency_and_units_are_partitioned_not_pooled(self) -> None:
        rows = [
            _row(row_id="cad-1", source_id="source-1", location="Chesterville", cash_bu=5.20, cash_mt=204.71),
            _row(row_id="cad-2", source_id="source-2", location="Johnstown", cash_bu=5.50, cash_mt=216.52),
            _row(
                row_id="usd",
                source_id="source-us",
                location="Ogdensburg",
                cash_bu=9.99,
                cash_mt=393.30,
                currency="USD",
            ),
        ]

        bundle = build_content_bundle(rows, cadence="daily", region=REGION, generated_at=NOW)
        facts = [fact for fact in bundle.facts["facts"] if fact["fact_type"] == "posted_bid_summary"]

        self.assertEqual({fact["unit"] for fact in facts}, {"CAD/bu", "CAD/MT"})
        self.assertEqual({fact["high"] for fact in facts}, {5.50, 216.52})
        self.assertEqual(bundle.qa["warnings"][0]["counts"]["currency_mismatch"], 1)
        self.assertEqual(bundle.status, "draft_needs_review")

    def test_freshness_and_minimum_coverage_gates_block_bad_inputs(self) -> None:
        stale = [
            _row(
                row_id="stale-1",
                source_id="source-1",
                location="Chesterville",
                captured_at=NOW - timedelta(hours=25),
            ),
            _row(
                row_id="stale-2",
                source_id="source-2",
                location="Johnstown",
                captured_at=NOW - timedelta(hours=30),
            ),
        ]
        stale_bundle = build_content_bundle(stale, cadence="daily", region=REGION, generated_at=NOW)
        low_coverage = build_content_bundle(
            [_row(row_id="only", source_id="source-1", location="Chesterville")],
            cadence="daily",
            region=REGION,
            generated_at=NOW,
        )

        self.assertEqual(stale_bundle.status, "blocked")
        self.assertIn("stale", stale_bundle.qa["warnings"][0]["counts"])
        self.assertEqual(low_coverage.status, "blocked")
        self.assertTrue(any(item["code"] == "minimum_source_coverage" for item in low_coverage.qa["failures"]))

    def test_every_rendered_numeric_claim_has_fact_lineage(self) -> None:
        bundle = build_content_bundle(_healthy_rows(), cadence="daily", region=REGION, generated_at=NOW)
        facts = {fact["fact_id"]: fact for fact in bundle.facts["facts"]}
        claims = list(bundle.artifacts["email"]["claims"]) + list(bundle.artifacts["site"]["claims"])
        for social in bundle.artifacts["social"]:
            claims.extend(social["claims"])

        self.assertTrue(claims)
        for claim in claims:
            self.assertIn(claim["fact_id"], facts)
            self.assertTrue(facts[claim["fact_id"]]["source_row_ids"])

    def test_identical_inputs_are_persisted_idempotently(self) -> None:
        db = _DraftSession()
        org_id = uuid.uuid4()
        first = generate_content_draft(
            db,
            org_id=org_id,
            cadence="daily",
            generated_at=NOW,
            rows=_healthy_rows(),
        )
        second = generate_content_draft(
            db,
            org_id=org_id,
            cadence="daily",
            generated_at=NOW,
            rows=_healthy_rows(),
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertIs(first.draft, second.draft)
        self.assertEqual(db.add_count, 1)
        self.assertEqual(db.commit_count, 1)

    def test_generation_is_draft_only_and_never_calls_sender(self) -> None:
        with patch("app.services.smtp_sender.send_smtp_message") as sender:
            bundle = build_content_bundle(_healthy_rows(), cadence="daily", region=REGION, generated_at=NOW)

        sender.assert_not_called()
        self.assertIn(bundle.status, ALLOWED_STATUSES)
        self.assertTrue(all(artifact["publication_status"] in ALLOWED_STATUSES for artifact in [
            bundle.artifacts["email"],
            bundle.artifacts["site"],
            *bundle.artifacts["social"],
        ]))
        serialized = str(bundle.artifacts).casefold()
        self.assertNotIn("smtp", serialized)
        self.assertNotIn("publish_url", serialized)


if __name__ == "__main__":
    unittest.main()
