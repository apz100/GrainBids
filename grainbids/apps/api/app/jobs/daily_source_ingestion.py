from __future__ import annotations

import uuid

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.services.source_file_ingestion import ingest_source_file


def main() -> int:
    if not settings.daily_source_file_path:
        raise RuntimeError("DAILY_SOURCE_FILE_PATH is required")
    if not settings.daily_source_id:
        raise RuntimeError("DAILY_SOURCE_ID is required")
    if not settings.daily_commodity_id:
        raise RuntimeError("DAILY_COMMODITY_ID is required")

    db = get_sessionmaker()()
    try:
        result = ingest_source_file(
            db,
            source_file_path=settings.daily_source_file_path,
            source_name=settings.daily_source_name,
            source_id=uuid.UUID(settings.daily_source_id),
            commodity_id=uuid.UUID(settings.daily_commodity_id),
        )
        print(
            f"ingestion_run={result.run_id} status={result.status} "
            f"raw_rows={result.raw_row_count} normalized_rows={result.normalized_row_count} "
            f"alerts_created={result.created_alert_count} alerts_deduped={result.deduped_alert_count}"
        )
        return 0 if result.status == "completed" else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
