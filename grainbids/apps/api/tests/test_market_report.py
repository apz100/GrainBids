from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.models.newsletter_subscriber import NewsletterSubscriber  # noqa: E402
from app.services.market_report import (  # noqa: E402
    _build_message,
    compile_market_report,
    deliver_market_report,
)


def _bid(
    *,
    cash: float,
    basis: float,
    location: str,
    captured_at: str = "2026-07-14T13:00:00+00:00",
) -> dict[str, object]:
    return {
        "cash_price_bu": cash,
        "basis": basis,
        "location": location,
        "company_name": "Example Grain",
        "delivery_label": "July 2026",
        "captured_at": captured_at,
    }


class _ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _ScalarRows(self.rows)

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class _DryRunSession:
    def __init__(self, subscribers):
        self.subscribers = subscribers

    def execute(self, _query):
        return _Result(self.subscribers)


class _SendSession(_DryRunSession):
    def __init__(self, subscribers, existing=None):
        super().__init__(subscribers)
        self.existing = existing
        self.execute_count = 0
        self.added = []
        self.commit_count = 0

    def execute(self, _query):
        self.execute_count += 1
        if self.execute_count == 1:
            return _Result(self.subscribers)
        return _Result([self.existing] if self.existing is not None else [])

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commit_count += 1


class MarketReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generated_at = datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc)

    def test_report_sorts_bids_and_calculates_summary(self) -> None:
        report = compile_market_report(
            {
                "Corn": [
                    _bid(cash=5.15, basis=1.10, location="Prescott"),
                    _bid(cash=5.45, basis=1.30, location="Johnstown"),
                    _bid(cash=5.25, basis=1.20, location="Embrun"),
                    _bid(cash=5.05, basis=1.00, location="Winchester"),
                ],
                "Soybeans": [],
                "Wheat": [],
            },
            generated_at=self.generated_at,
            region="Eastern Ontario",
        )

        corn = report.sections[0]
        self.assertEqual(report.issue_key, "2026-W29")
        self.assertEqual(corn["market_count"], 4)
        self.assertEqual(corn["median_cash_price_bu"], 5.20)
        self.assertAlmostEqual(corn["cash_spread_bu"], 0.40)
        self.assertEqual(corn["top_bids"][0]["location"], "Johnstown")
        self.assertIn("$5.45/bu", report.text)
        self.assertIn("No current canonical bids were available", report.html)

    def test_dry_run_counts_subscribers_without_writing_or_sending(self) -> None:
        report = compile_market_report(
            {commodity: [] for commodity in ("Corn", "Soybeans", "Wheat")},
            generated_at=self.generated_at,
            region="Eastern Ontario",
        )
        subscribers = [NewsletterSubscriber(email="one@example.com"), NewsletterSubscriber(email="two@example.com")]
        db = _DryRunSession(subscribers)

        with patch("app.services.market_report.send_smtp_message") as sender:
            summary = deliver_market_report(db, org_id=uuid.uuid4(), report=report)

        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.targeted, 2)
        sender.assert_not_called()

    def test_email_contains_personalization_and_unsubscribe_link(self) -> None:
        report = compile_market_report(
            {commodity: [] for commodity in ("Corn", "Soybeans", "Wheat")},
            generated_at=self.generated_at,
            region="Eastern Ontario",
        )
        token = uuid.uuid4()
        subscriber = NewsletterSubscriber(
            email="adam@example.com",
            first_name="Adam",
            unsubscribe_token=token,
        )
        with (
            patch.object(settings, "market_report_email_from", "reports@grainbids.com"),
            patch.object(
                settings,
                "market_report_unsubscribe_url",
                "https://api.grainbids.com/api/newsletter/unsubscribe",
            ),
        ):
            message = _build_message(report, subscriber)

        self.assertEqual(message["To"], "adam@example.com")
        self.assertIn(str(token), message["List-Unsubscribe"])
        self.assertIn("Hi Adam", message.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("Unsubscribe", message.get_body(preferencelist=("html",)).get_content())

    def test_send_records_delivery_and_rerun_skips_same_issue(self) -> None:
        report = compile_market_report(
            {commodity: [] for commodity in ("Corn", "Soybeans", "Wheat")},
            generated_at=self.generated_at,
            region="Eastern Ontario",
        )
        subscriber = NewsletterSubscriber(
            id=uuid.uuid4(),
            email="adam@example.com",
            unsubscribe_token=uuid.uuid4(),
        )
        org_id = uuid.uuid4()
        db = _SendSession([subscriber])
        config = (
            patch.object(settings, "market_report_email_enabled", True),
            patch.object(settings, "market_report_email_from", "reports@grainbids.com"),
            patch.object(
                settings,
                "market_report_unsubscribe_url",
                "https://api.grainbids.com/api/newsletter/unsubscribe",
            ),
            patch.object(settings, "alert_smtp_host", "smtp.example.com"),
        )
        with config[0], config[1], config[2], config[3], patch(
            "app.services.market_report.send_smtp_message"
        ) as sender:
            summary = deliver_market_report(db, org_id=org_id, report=report, send=True)

        self.assertEqual(summary.sent, 1)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].status, "sent")
        sender.assert_called_once()

        rerun_db = _SendSession([subscriber], existing=db.added[0])
        with config[0], config[1], config[2], config[3], patch(
            "app.services.market_report.send_smtp_message"
        ) as rerun_sender:
            rerun = deliver_market_report(rerun_db, org_id=org_id, report=report, send=True)

        self.assertEqual(rerun.skipped, 1)
        rerun_sender.assert_not_called()


if __name__ == "__main__":
    unittest.main()
