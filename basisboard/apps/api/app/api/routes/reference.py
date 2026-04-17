from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, asc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.source import Source


router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/sources")
def list_sources(
    org_id: uuid.UUID | None = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query: Select[tuple[Source]] = select(Source)

    if org_id is not None:
        query = query.where(Source.org_id == org_id)
    if active_only:
        query = query.where(Source.is_active.is_(True))

    rows = db.execute(query.order_by(asc(Source.name)).limit(limit)).scalars().all()

    return {
        "rows": [
            {
                "id": str(row.id),
                "org_id": str(row.org_id),
                "name": row.name,
                "source_type": row.source_type,
                "url": row.url,
                "location_name": row.location_name,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.get("/commodities")
def list_commodities(
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Commodity).order_by(asc(Commodity.name)).limit(limit)).scalars().all()

    return {
        "rows": [
            {
                "id": str(row.id),
                "name": row.name,
                "unit": row.unit,
                "conversion_factor": float(row.conversion_factor) if row.conversion_factor is not None else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }
