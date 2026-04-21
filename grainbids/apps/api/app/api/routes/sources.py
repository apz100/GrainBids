from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.organization import Organization
from app.models.source import Source
from app.services.source_orchestration import list_sources_with_health, run_source_refresh, seed_sources_from_registry


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
def list_sources(db: Session = Depends(get_db)):
    rows = list_sources_with_health(db)
    return {
        "rows": rows,
        "count": len(rows),
    }


@router.post("/seed")
def seed_sources(
    org_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    resolved_org_id = org_id or _default_org_id(db)
    created = seed_sources_from_registry(db, org_id=resolved_org_id)
    return {"created": created}


@router.post("/{source_id}/refresh")
def refresh_source_by_id(
    source_id: uuid.UUID,
    commodity_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    source = db.execute(select(Source).where(Source.id == source_id)).scalar_one_or_none()
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
        "error_message": result.error_message,
    }
    if status >= 400:
        raise HTTPException(status_code=status, detail=payload)
    return {"result": payload}


def _default_org_id(db: Session) -> uuid.UUID:
    org = db.execute(select(Organization).order_by(Organization.created_at.asc()).limit(1)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=400, detail="No organization exists. Create one first.")
    return org.id


def _default_commodity_id(db: Session) -> uuid.UUID:
    commodity = db.execute(select(Commodity).order_by(Commodity.created_at.asc()).limit(1)).scalar_one_or_none()
    if commodity is None:
        raise HTTPException(status_code=400, detail="No commodity exists. Create one first.")
    return commodity.id
