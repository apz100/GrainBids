from __future__ import annotations

from dataclasses import asdict
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.source_file_ingestion import ingest_source_file, list_ingestion_runs


router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.get("/runs")
def get_ingestion_runs(
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return {
        "rows": [
            {
                "id": str(row.id),
                "source_name": row.source_name,
                "source_identifier": row.source_identifier,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "status": row.status,
                "raw_row_count": row.raw_row_count,
                "normalized_row_count": row.normalized_row_count,
                "error_message": row.error_message,
            }
            for row in list_ingestion_runs(db, limit=limit)
        ]
    }


@router.post("/source-file/run")
def run_source_file_ingestion(
    source_file_path: str | None = Query(None),
    source_name: str | None = Query(None),
    source_id: uuid.UUID | None = Query(None),
    commodity_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    file_path = source_file_path or settings.daily_source_file_path
    name = source_name or settings.daily_source_name
    resolved_source_id = source_id or _parse_uuid(settings.daily_source_id, "DAILY_SOURCE_ID")
    resolved_commodity_id = commodity_id or _parse_uuid(settings.daily_commodity_id, "DAILY_COMMODITY_ID")

    if not file_path:
        raise HTTPException(status_code=400, detail="source_file_path is required")

    result = ingest_source_file(
        db,
        source_file_path=file_path,
        source_name=name,
        source_id=resolved_source_id,
        commodity_id=resolved_commodity_id,
    )

    payload = _serialize_result(result)
    status_code = 500 if result.status == "failed" else 200
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=payload)
    return {"result": payload}


def _parse_uuid(value: str, setting_name: str) -> uuid.UUID:
    if not value:
        raise HTTPException(status_code=400, detail=f"{setting_name} is required")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{setting_name} must be a valid UUID") from exc


def _serialize_result(result):
    payload = asdict(result)
    if payload.get("run_id") is not None:
        payload["run_id"] = str(payload["run_id"])
    return payload
