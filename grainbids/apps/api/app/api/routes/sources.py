from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.source import Source
from app.services.source_orchestration import list_sources_with_health, run_source_refresh, seed_sources_from_registry
from app.services.source_registry import list_pilot_adapter_keys


router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/module")
def module_info():
    return {
        "module": "sources",
        "primary_routes": [
            "/api/sources",
            "/api/sources/{id}/refresh",
            "/api/ingestion/sla",
        ],
    }


@router.get("")
def list_sources(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = list_sources_with_health(db, org_id=context.org_id)
    return {
        "rows": rows,
        "count": len(rows),
    }


@router.post("/seed")
def seed_sources(
    scope: str = Query("pilot", pattern="^(pilot|all)$"),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter_keys = list_pilot_adapter_keys() if scope == "pilot" else None
    created = seed_sources_from_registry(db, org_id=context.org_id, adapter_keys=adapter_keys)
    return {"created": created, "scope": scope, "adapter_keys": adapter_keys or "all"}


@router.post("/{source_id}/refresh")
def refresh_source_by_id(
    source_id: uuid.UUID,
    commodity_id: uuid.UUID | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.execute(select(Source).where(Source.id == source_id, Source.org_id == context.org_id)).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    if not source.is_active:
        raise HTTPException(status_code=400, detail="source is inactive")

    resolved_commodity_id = commodity_id or _default_commodity_id(db)
    result = run_source_refresh(
        db,
        source=source,
        commodity_id=resolved_commodity_id,
        trigger_type="manual",
    )
    status = 200 if result.status == "completed" else 500
    payload = {
        "source_id": str(result.source_id),
        "source_name": result.source_name,
        "status": result.status,
        "attempts": result.attempts,
        "duration_ms": result.duration_ms,
        "row_count": result.row_count,
        "alerts_created": result.created_alert_count,
        "alerts_deduped": result.deduped_alert_count,
        "error_message": result.error_message,
    }
    if status >= 400:
        raise HTTPException(status_code=status, detail=payload)
    return {"result": payload}


def _default_commodity_id(db: Session) -> uuid.UUID:
    commodity = db.execute(select(Commodity).order_by(Commodity.created_at.asc()).limit(1)).scalar_one_or_none()
    if commodity is None:
        raise HTTPException(status_code=400, detail="No commodity exists. Create one first.")
    return commodity.id
