from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.commodity import Commodity
from app.services.source_file_ingestion import ingest_source_file, run_scheduled_file_ingestion_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GrainBids file-source ingestion cycle.")
    parser.add_argument("--single-source", action="store_true", help="Use DAILY_SOURCE_* env vars for one source.")
    parser.add_argument("--commodity-id", type=str, default="", help="Commodity UUID override for scheduled cycle.")
    parser.add_argument("--max-attempts", type=int, default=0, help="Retry attempts per file source.")
    args = parser.parse_args()

    db = get_sessionmaker()()
    try:
        if args.single_source:
            return _run_single_source(db)

        commodity_id = _resolve_commodity_id(db, args.commodity_id)
        max_attempts = args.max_attempts if args.max_attempts > 0 else settings.file_ingestion_max_attempts
        results = run_scheduled_file_ingestion_cycle(
            db,
            commodity_id=commodity_id,
            max_attempts=max_attempts,
        )
        failed = [row for row in results if row.status != "completed"]
        for row in results:
            print(
                f"source={row.source_name} status={row.status} attempt={row.attempt_number}/{row.max_attempts} "
                f"raw={row.raw_row_count} normalized={row.normalized_row_count} "
                f"parse_success={row.parse_success_rate} rejected={row.rejected_row_count} duplicates={row.duplicate_key_count}"
            )
        print(f"cycle_sources={len(results)} failed={len(failed)}")
        return 0 if len(failed) == 0 else 1
    finally:
        db.close()


def _run_single_source(db) -> int:
    if not settings.daily_source_file_path:
        raise RuntimeError("DAILY_SOURCE_FILE_PATH is required for --single-source mode")
    if not settings.daily_source_id:
        raise RuntimeError("DAILY_SOURCE_ID is required for --single-source mode")
    commodity_id = uuid.UUID(settings.daily_commodity_id) if settings.daily_commodity_id else None

    result = ingest_source_file(
        db,
        source_file_path=settings.daily_source_file_path,
        source_name=settings.daily_source_name,
        source_id=uuid.UUID(settings.daily_source_id),
        commodity_id=commodity_id,
        trigger_type="scheduled",
        attempt_number=1,
        max_attempts=1,
    )
    print(
        f"ingestion_run={result.run_id} status={result.status} raw_rows={result.raw_row_count} "
        f"normalized_rows={result.normalized_row_count} parse_success={result.parse_success_rate} "
        f"rejected={result.rejected_row_count} duplicates={result.duplicate_key_count}"
    )
    return 0 if result.status == "completed" else 1


def _resolve_commodity_id(db, override: str) -> uuid.UUID:
    if override:
        return uuid.UUID(override)
    if settings.daily_commodity_id:
        return uuid.UUID(settings.daily_commodity_id)
    commodity = db.execute(select(Commodity).order_by(Commodity.created_at.asc()).limit(1)).scalar_one_or_none()
    if commodity is None:
        raise RuntimeError("No commodity exists; create one commodity before running file ingestion jobs.")
    return commodity.id


if __name__ == "__main__":
    raise SystemExit(main())
