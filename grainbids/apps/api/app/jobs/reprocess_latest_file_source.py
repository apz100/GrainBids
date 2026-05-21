from __future__ import annotations

import argparse
import uuid

from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.services.ingestion_diagnostics import build_ingestion_diagnostics
from app.services.source_file_ingestion import reprocess_latest_file_source


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprocess the latest GrainBids file-source snapshot and print diagnostics.")
    parser.add_argument("--org-id", type=str, default="", help="Organization UUID override.")
    parser.add_argument("--source-id", type=str, default="", help="Optional source UUID filter.")
    parser.add_argument("--source-file-path", type=str, default="", help="Optional file path override for reprocess.")
    parser.add_argument("--duplicate-limit", type=int, default=10, help="Max duplicate-company rows to print.")
    parser.add_argument("--skip-diagnostics", action="store_true", help="Only print the ingestion result.")
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        db.execute(text("SET statement_timeout TO '10min'"))
        org_id = _resolve_org_id(db, args.org_id)
        source_id = uuid.UUID(args.source_id) if args.source_id else None

        target, result = reprocess_latest_file_source(
            db,
            org_id=org_id,
            source_id=source_id,
            source_file_path_override=args.source_file_path or settings.reprocess_source_file_path_override,
        )
        print(
            "reprocessed "
            f"source={target.source_name} source_id={target.source_id} "
            f"input_snapshot={target.snapshot_id} file={target.source_file_path} "
            f"run_id={result.run_id} status={result.status} normalized={result.normalized_row_count} "
            f"duplicates={result.duplicate_key_count} rejected={result.rejected_row_count}"
        )

        if args.skip_diagnostics:
            return 0 if result.status == "completed" else 1

        diagnostics = build_ingestion_diagnostics(
            db,
            org_id=org_id,
            source_id=source_id or target.source_id,
            duplicate_limit=max(1, args.duplicate_limit),
        )
        _print_diagnostics(diagnostics)
        return 0 if result.status == "completed" else 1
    finally:
        db.close()


def _resolve_org_id(db, override: str) -> uuid.UUID:
    if override:
        return uuid.UUID(override)
    org = db.execute(text("SELECT id FROM organizations ORDER BY created_at ASC LIMIT 1")).scalar_one_or_none()
    if org is None:
        raise RuntimeError("No organization exists. Provide --org-id after creating one.")
    return org


def _print_diagnostics(payload: dict[str, object]) -> None:
    latest_snapshot = payload.get("latest_snapshot")
    if isinstance(latest_snapshot, dict):
        print(
            "latest_snapshot "
            f"id={latest_snapshot.get('id')} source={latest_snapshot.get('source_name')} "
            f"file={latest_snapshot.get('source_file_path')} rows={latest_snapshot.get('row_count')} "
            f"canonical={latest_snapshot.get('canonical_row_count')} duplicates={latest_snapshot.get('duplicate_market_key_count')}"
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
