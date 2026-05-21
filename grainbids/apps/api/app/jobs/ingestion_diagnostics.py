from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.organization import Organization
from app.services.ingestion_diagnostics import (
    build_ingestion_diagnostics,
    recompute_latest_snapshot_canonical_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or recompute latest GrainBids ingestion snapshot state.")
    parser.add_argument("--org-id", type=str, default="", help="Organization UUID override.")
    parser.add_argument("--source-id", type=str, default="", help="Optional source UUID filter.")
    parser.add_argument("--duplicate-limit", type=int, default=10, help="Max duplicate-company rows to print.")
    parser.add_argument(
        "--recompute-latest",
        action="store_true",
        help="Recompute canonical rows for the latest snapshot before printing diagnostics.",
    )
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        org_id = _resolve_org_id(db, args.org_id)
        source_id = uuid.UUID(args.source_id) if args.source_id else None

        if args.recompute_latest:
            result = recompute_latest_snapshot_canonical_rows(
                db,
                org_id=org_id,
                source_id=source_id,
            )
            print(
                "recomputed "
                f"snapshot={result['snapshot_id']} source={result['source_name']} "
                f"impacted_keys={result['impacted_keys']} updated_rows={result['updated_rows']} "
                f"canonical_rows={result['canonical_rows']}"
            )

        diagnostics = build_ingestion_diagnostics(
            db,
            org_id=org_id,
            source_id=source_id,
            duplicate_limit=max(1, args.duplicate_limit),
        )
        _print_diagnostics(diagnostics)
        return 0
    finally:
        db.close()


def _resolve_org_id(db, override: str) -> uuid.UUID:
    if override:
        return uuid.UUID(override)
    org = db.execute(select(Organization).order_by(Organization.created_at.asc()).limit(1)).scalar_one_or_none()
    if org is None:
        raise RuntimeError("No organization exists. Provide --org-id after creating one.")
    return org.id


def _print_diagnostics(payload: dict[str, object]) -> None:
    latest_run = payload.get("latest_run")
    if isinstance(latest_run, dict):
        print(
            "latest_run "
            f"id={latest_run.get('id')} source={latest_run.get('source_name')} status={latest_run.get('status')} "
            f"normalized={latest_run.get('normalized_row_count')} duplicates={latest_run.get('duplicate_key_count')} "
            f"rejected={latest_run.get('rejected_row_count')} duration_ms={latest_run.get('duration_ms')}"
        )
    else:
        print("latest_run none")

    latest_snapshot = payload.get("latest_snapshot")
    if not isinstance(latest_snapshot, dict):
        print("latest_snapshot none")
        return

    print(
        "latest_snapshot "
        f"id={latest_snapshot.get('id')} source={latest_snapshot.get('source_name')} "
        f"captured_at={latest_snapshot.get('captured_at')} rows={latest_snapshot.get('row_count')} "
        f"canonical={latest_snapshot.get('canonical_row_count')} non_canonical={latest_snapshot.get('non_canonical_row_count')} "
        f"duplicate_market_keys={latest_snapshot.get('duplicate_market_key_count')}"
    )

    duplicate_rows = payload.get("duplicate_candidates_by_company") or []
    if not duplicate_rows:
        print("duplicate_candidates_by_company none")
        return

    for row in duplicate_rows:
        print(
            "duplicate_company "
            f"name={row.get('company_name')} duplicate_keys={row.get('duplicate_market_keys')} "
            f"candidates={row.get('candidate_rows')} alternates={row.get('alternate_rows')} "
            f"sample_markets={'; '.join(row.get('sample_markets') or [])}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
