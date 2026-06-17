from __future__ import annotations

import uuid
from decimal import Decimal
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.watchlist import Watchlist
from app.models.watchlist_automation import WatchlistAutomation
from app.services.watchlist_automation import (
    delete_watchlist_automation,
    load_watchlist_preview_rows,
    run_watchlist_digest,
    serialize_watchlist_automation,
    set_watchlist_automation,
    sync_watchlist_automation_after_watchlist_update,
)


router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _to_basis_float(value: Decimal | float | int | None) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    if abs(number) >= 10:
        return number / 100.0
    return number


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
    automation_rows = db.execute(
        select(WatchlistAutomation).where(WatchlistAutomation.org_id == context.org_id)
    ).scalars().all()
    automation_by_watchlist_id = {row.watchlist_id: row for row in automation_rows}
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
                "automation": _serialize_watchlist_automation_row(automation_by_watchlist_id.get(row.id)),
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
    context: RequestContext = Depends(require_admin),
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
    context: RequestContext = Depends(require_admin),
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
    sync_watchlist_automation_after_watchlist_update(db, watchlist=row)
    return {"id": str(row.id), "name": row.name, "is_active": row.is_active}


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    delete_watchlist_automation(db, watchlist=row)
    db.delete(row)
    db.commit()
    return {"deleted": str(watchlist_id)}


@router.get("/{watchlist_id}/preview")
def preview_watchlist(
    watchlist_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    watchlist = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="watchlist not found")

    rows = load_watchlist_preview_rows(db, watchlist=watchlist, limit=limit)
    return {
        "watchlist": {
            "id": str(watchlist.id),
            "name": watchlist.name,
            "filters_json": watchlist.filters_json or {},
            "is_active": watchlist.is_active,
        },
        "rows": rows,
    }


@router.get("/{watchlist_id}/automation")
def get_watchlist_automation(
    watchlist_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    watchlist = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return serialize_watchlist_automation(db, watchlist=watchlist)


@router.put("/{watchlist_id}/automation")
def set_watchlist_automation_route(
    watchlist_id: uuid.UUID,
    is_enabled: bool = Query(True),
    digest_enabled: bool = Query(True),
    alert_promotion_enabled: bool = Query(True),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    watchlist = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    result = set_watchlist_automation(
        db,
        watchlist=watchlist,
        is_enabled=is_enabled,
        digest_enabled=digest_enabled,
        alert_promotion_enabled=alert_promotion_enabled,
    )
    return {
        "automation": {
            "id": str(result.automation_id),
            "watchlist_id": str(result.watchlist_id),
            "saved_search_id": str(result.saved_search_id) if result.saved_search_id else None,
            "alert_rule_id": str(result.alert_rule_id) if result.alert_rule_id else None,
            "is_enabled": result.is_enabled,
            "digest_enabled": result.digest_enabled,
            "alert_promotion_enabled": result.alert_promotion_enabled,
        }
    }


@router.get("/{watchlist_id}/automation/preview")
def preview_watchlist_automation(
    watchlist_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    watchlist = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return serialize_watchlist_automation(db, watchlist=watchlist, limit=limit)


@router.post("/{watchlist_id}/automation/run")
def run_watchlist_automation_route(
    watchlist_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    watchlist = db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.org_id == context.org_id)
    ).scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    result = run_watchlist_digest(db, watchlist=watchlist, limit=limit)
    return {
        "automation_run": {
            "automation_id": str(result.automation_id),
            "watchlist_id": str(result.watchlist_id),
            "row_count": result.row_count,
            "sent": result.sent,
            "status": result.status,
            "error_message": result.error_message,
        }
    }


def _serialize_watchlist_automation_row(row: WatchlistAutomation | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "watchlist_id": str(row.watchlist_id),
        "is_enabled": row.is_enabled,
        "digest_enabled": row.digest_enabled,
        "alert_promotion_enabled": row.alert_promotion_enabled,
        "linked_saved_search_id": str(row.linked_saved_search_id) if row.linked_saved_search_id else None,
        "linked_alert_rule_id": str(row.linked_alert_rule_id) if row.linked_alert_rule_id else None,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_digest_row_count": row.last_digest_row_count,
        "last_error_message": row.last_error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
