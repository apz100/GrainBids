from __future__ import annotations

from dataclasses import asdict
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.source import Source
from app.services.source_orchestration import build_sla_summary
from app.services.source_file_ingestion import ingest_source_file, list_ingestion_runs, run_scheduled_file_ingestion_cycle


router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.get("/runs")
def get_ingestion_runs(
    limit: int = Query(25, ge=1, le=200),
    _context: RequestContext = Depends(get_request_context),
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
                "trigger_type": row.trigger_type,
                "attempt_number": row.attempt_number,
                "max_attempts": row.max_attempts,
                "raw_row_count": row.raw_row_count,
                "normalized_row_count": row.normalized_row_count,
                "created_alert_count": row.created_alert_count,
                "deduped_alert_count": row.deduped_alert_count,
                "duplicate_key_count": row.duplicate_key_count,
                "rejected_row_count": row.rejected_row_count,
                "missing_required_count": row.missing_required_count,
                "row_reject_reasons": row.row_reject_reasons_json,
                "duration_ms": row.duration_ms,
                "parse_success_rate": float(row.parse_success_rate) if row.parse_success_rate is not None else None,
                "schema_drift_count": row.schema_drift_count,
                "error_message": row.error_message,
            }
            for row in list_ingestion_runs(db, limit=limit, org_id=_context.org_id)
        ]
    }


@router.get("/sla")
def get_ingestion_sla(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    return build_sla_summary(db, org_id=context.org_id)


@router.post("/source-file/run")
def run_source_file_ingestion(
    source_file_path: str | None = Query(None),
    source_name: str | None = Query(None),
    source_id: uuid.UUID | None = Query(None),
    commodity_id: uuid.UUID | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    file_path = source_file_path or settings.daily_source_file_path
    name = source_name or settings.daily_source_name
    resolved_source_id = source_id or _parse_uuid(settings.daily_source_id, "DAILY_SOURCE_ID")
    resolved_commodity_id = commodity_id or _parse_uuid(settings.daily_commodity_id, "DAILY_COMMODITY_ID")
    _assert_source_org_scope(db, source_id=resolved_source_id, org_id=context.org_id)

    if not file_path:
        raise HTTPException(status_code=400, detail="source_file_path is required")

    result = ingest_source_file(
        db,
        source_file_path=file_path,
        source_name=name,
        source_id=resolved_source_id,
        commodity_id=resolved_commodity_id,
        trigger_type="manual",
        attempt_number=1,
        max_attempts=1,
    )

    payload = _serialize_result(result)
    status_code = 500 if result.status == "failed" else 200
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=payload)
    return {"result": payload}


@router.post("/source-files/run")
def run_scheduled_source_file_cycle(
    commodity_id: uuid.UUID | None = Query(None),
    max_attempts: int | None = Query(None, ge=1, le=10),
    source_ids: list[uuid.UUID] | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_commodity_id = commodity_id or _default_commodity_id(db)
    _assert_commodity_exists(db, commodity_id=resolved_commodity_id)
    if source_ids:
        for source_id in source_ids:
            _assert_source_org_scope(db, source_id=source_id, org_id=context.org_id)

    results = run_scheduled_file_ingestion_cycle(
        db,
        commodity_id=resolved_commodity_id,
        org_id=context.org_id,
        max_attempts=max_attempts,
        source_ids=source_ids,
    )
    failed = [result for result in results if result.status != "completed"]
    return {
        "summary": {
            "total_sources": len(results),
            "completed_sources": len(results) - len(failed),
            "failed_sources": len(failed),
        },
        "results": [_serialize_result(result) for result in results],
    }


def _assert_source_org_scope(db: Session, *, source_id: uuid.UUID, org_id: uuid.UUID) -> None:
    source = db.execute(select(Source.id).where(Source.id == source_id, Source.org_id == org_id)).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found for this organization")


def _parse_uuid(value: str, setting_name: str) -> uuid.UUID:
    if not value:
        raise HTTPException(status_code=400, detail=f"{setting_name} is required")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{setting_name} must be a valid UUID") from exc


def _default_commodity_id(db: Session) -> uuid.UUID:
    commodity = db.execute(select(Commodity).order_by(Commodity.created_at.asc()).limit(1)).scalar_one_or_none()
    if commodity is None:
        raise HTTPException(status_code=400, detail="No commodity exists. Create one first.")
    return commodity.id


def _assert_commodity_exists(db: Session, *, commodity_id: uuid.UUID) -> None:
    commodity = db.execute(select(Commodity.id).where(Commodity.id == commodity_id)).scalar_one_or_none()
    if commodity is None:
        raise HTTPException(status_code=404, detail="commodity not found")


def _serialize_result(result):
    payload = asdict(result)
    for key, value in list(payload.items()):
        if isinstance(value, uuid.UUID):
            payload[key] = str(value)
    return payload
