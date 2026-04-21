from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.commodity import Commodity
from app.models.ingestion_run import IngestionRun
from app.models.source import Source
from app.services.upload_csv import persist_normalized_rows


@dataclass
class SourceFileIngestionResult:
    run_id: uuid.UUID
    source_name: str
    source_identifier: str
    status: str
    raw_row_count: int | None
    normalized_row_count: int | None
    error_message: str | None


def _read_source_file(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    if not path.exists():
        raise ValueError(f"source file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"source path is not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        raise ValueError("source file must be .csv, .xlsx, or .xls")

    headers = [str(column) for column in df.columns.tolist()]
    rows = df.where(pd.notnull(df), None).to_dict(orient="records")
    return rows, headers


def _get_source(db: Session, source_id: uuid.UUID) -> Source:
    source = db.execute(select(Source).where(Source.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ValueError("source_id not found")
    return source


def _get_commodity(db: Session, commodity_id: uuid.UUID) -> Commodity:
    commodity = db.execute(select(Commodity).where(Commodity.id == commodity_id)).scalar_one_or_none()
    if commodity is None:
        raise ValueError("commodity_id not found")
    return commodity


def ingest_source_file(
    db: Session,
    *,
    source_file_path: str,
    source_name: str,
    source_id: uuid.UUID,
    commodity_id: uuid.UUID,
    captured_at: datetime | None = None,
) -> SourceFileIngestionResult:
    source_identifier = str(Path(source_file_path))
    run = IngestionRun(
        source_name=source_name,
        source_identifier=source_identifier,
        started_at=datetime.now(timezone.utc),
        status="running",
        trigger_type="manual",
        attempt_number=1,
        max_attempts=1,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        started = datetime.now(timezone.utc)
        source = _get_source(db, source_id)
        commodity = _get_commodity(db, commodity_id)
        rows, headers = _read_source_file(Path(source_file_path))

        persisted = persist_normalized_rows(
            db,
            source=source,
            commodity=commodity,
            rows=rows,
            headers=headers,
            captured_at=captured_at,
            raw_payload_json={
                "source_file_path": source_identifier,
                "headers": headers,
                "ingestion_run_id": str(run.id),
            },
        )

        run.raw_row_count = persisted.raw_row_count
        run.normalized_row_count = persisted.inserted_rows
        run.duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        run.parse_success_rate = 1.0
        run.schema_drift_count = 0
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
    except Exception as exc:
        db.rollback()
        run = db.execute(select(IngestionRun).where(IngestionRun.id == run.id)).scalar_one()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = str(exc)
        db.commit()
        db.refresh(run)

    return SourceFileIngestionResult(
        run_id=run.id,
        source_name=run.source_name,
        source_identifier=run.source_identifier,
        status=run.status,
        raw_row_count=run.raw_row_count,
        normalized_row_count=run.normalized_row_count,
        error_message=run.error_message,
    )


def list_ingestion_runs(db: Session, *, limit: int = 25) -> list[IngestionRun]:
    return db.execute(
        select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(limit)
    ).scalars().all()
