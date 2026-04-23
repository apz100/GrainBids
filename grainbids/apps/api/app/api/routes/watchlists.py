from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.models.watchlist import Watchlist


router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


@router.get("/module")
def module_info():
    return {
        "module": "watchlists",
        "primary_routes": ["/api/watchlists"],
    }


@router.get("")
def list_watchlists(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Watchlist).where(Watchlist.org_id == context.org_id).order_by(desc(Watchlist.updated_at))
    ).scalars().all()
    return {
        "rows": [
            {
                "id": str(row.id),
                "org_id": str(row.org_id),
                "name": row.name,
                "filters_json": row.filters_json,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    }


@router.post("")
def create_watchlist(
    name: str = Query(..., min_length=2, max_length=200),
    is_active: bool = Query(True),
    location: str | None = Query(None),
    commodity_name: str | None = Query(None),
    source_name: str | None = Query(None),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    filters = {}
    if location:
        filters["location"] = location.strip()
    if commodity_name:
        filters["commodity_name"] = commodity_name.strip()
    if source_name:
        filters["source_name"] = source_name.strip()
    row = Watchlist(org_id=context.org_id, name=name.strip(), is_active=is_active, filters_json=filters or {})
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "name": row.name}


@router.patch("/{watchlist_id}")
def update_watchlist(
    watchlist_id: uuid.UUID,
    name: str | None = Query(None, min_length=2, max_length=200),
    is_active: bool | None = Query(None),
    location: str | None = Query(None),
    commodity_name: str | None = Query(None),
    source_name: str | None = Query(None),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    if name is not None:
        row.name = name.strip()
    if is_active is not None:
        row.is_active = is_active
    current_filters = dict(row.filters_json or {})
    if location is not None:
        if location.strip():
            current_filters["location"] = location.strip()
        else:
            current_filters.pop("location", None)
    if commodity_name is not None:
        if commodity_name.strip():
            current_filters["commodity_name"] = commodity_name.strip()
        else:
            current_filters.pop("commodity_name", None)
    if source_name is not None:
        if source_name.strip():
            current_filters["source_name"] = source_name.strip()
        else:
            current_filters.pop("source_name", None)
    row.filters_json = current_filters
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "name": row.name, "is_active": row.is_active}


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    db.delete(row)
    db.commit()
    return {"deleted": str(watchlist_id)}
