from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
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
    org_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    resolved_org = org_id or _default_org_id(db)
    rows = db.execute(
        select(Watchlist).where(Watchlist.org_id == resolved_org).order_by(desc(Watchlist.updated_at))
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
    org_id: uuid.UUID | None = Query(None),
    is_active: bool = Query(True),
    db: Session = Depends(get_db),
):
    resolved_org = org_id or _default_org_id(db)
    row = Watchlist(org_id=resolved_org, name=name.strip(), is_active=is_active, filters_json={})
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "name": row.name}


@router.patch("/{watchlist_id}")
def update_watchlist(
    watchlist_id: uuid.UUID,
    name: str | None = Query(None, min_length=2, max_length=200),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    row = db.execute(select(Watchlist).where(Watchlist.id == watchlist_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    if name is not None:
        row.name = name.strip()
    if is_active is not None:
        row.is_active = is_active
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "name": row.name, "is_active": row.is_active}


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    row = db.execute(select(Watchlist).where(Watchlist.id == watchlist_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    db.delete(row)
    db.commit()
    return {"deleted": str(watchlist_id)}


def _default_org_id(db: Session) -> uuid.UUID:
    org = db.execute(select(Organization).order_by(Organization.created_at.asc()).limit(1)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=400, detail="No organization exists. Create one first.")
    return org.id
