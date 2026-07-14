from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.organization import Organization
from app.services.market_report import build_market_report, deliver_market_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or deliver the weekly GrainBids market report.")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually deliver email. Without this flag the job is always a dry run.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry failed deliveries for this issue. Sent and pending records remain skipped.",
    )
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        organization = db.execute(
            select(Organization).order_by(Organization.created_at.asc()).limit(1)
        ).scalar_one_or_none()
        if organization is None:
            raise RuntimeError("No organization exists. Create one before generating a market report.")

        report = build_market_report(db, org_id=organization.id)
        summary = deliver_market_report(
            db,
            org_id=organization.id,
            report=report,
            send=args.send,
            retry_failed=args.retry_failed,
        )
        mode = "SEND" if args.send else "DRY RUN"
        print(f"[{mode}] {report.subject}")
        print(report.text)
        print(
            f"issue={summary.issue_key} targeted={summary.targeted} sent={summary.sent} "
            f"skipped={summary.skipped} failed={summary.failed}"
        )
        return 1 if summary.failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
