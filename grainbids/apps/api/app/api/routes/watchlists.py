from __future__ import annotations

import uuid
from decimal import Decimal
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.models.watchlist import Watchlist
from app.services.market_canonicalization import (
    canonical_commodity_name,
    canonical_location_name,
    canonical_source_name,
    normalize_text,
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

    filters = watchlist.filters_json or {}
    query = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
    )

    location = str(filters.get("location", "") or "").strip()
    commodity_name = str(filters.get("commodity_name", "") or "").strip()
    source_name = str(filters.get("source_name", "") or "").strip()
    if location:
        query = query.where(NormalizedPrice.location.ilike(f"%{location}%"))
    if commodity_name:
        query = query.where(NormalizedPrice.commodity_name.ilike(f"%{commodity_name}%"))
    if source_name:
        query = query.where(NormalizedPrice.source_name.ilike(f"%{source_name}%"))

    rows = db.execute(
        query.order_by(desc(PriceSnapshot.captured_at), desc(NormalizedPrice.cash_price_bu)).limit(limit)
    ).all()
    deduped_rows: list[tuple[NormalizedPrice, PriceSnapshot]] = []
    seen: set[str] = set()
    for price, snapshot in rows:
        dedupe_key = "|".join(
            [
                canonical_location_name(price.location) or "-",
                canonical_source_name(price.source_name) or "-",
                canonical_commodity_name(price.commodity_name) or "-",
                normalize_text(price.delivery_label) or normalize_text(price.delivery_end) or "-",
                normalize_text(price.futures_month) or "-",
            ]
        ).lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped_rows.append((price, snapshot))
        if len(deduped_rows) >= limit:
            break

    return {
        "watchlist": {
            "id": str(watchlist.id),
            "name": watchlist.name,
            "filters_json": watchlist.filters_json or {},
            "is_active": watchlist.is_active,
        },
        "rows": [
            {
                "id": str(price.id),
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": canonical_location_name(price.location) or "-",
                "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
                "source_name": canonical_source_name(price.source_name),
                "delivery_label": normalize_text(price.delivery_label) or normalize_text(price.delivery_end),
                "futures_month": normalize_text(price.futures_month),
                "futures_price": _to_float(price.futures_price),
                "futures_change": _to_float(getattr(price, "futures_change", None)),
                "basis": _to_basis_float(price.basis),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_mt": _to_float(price.cash_price_mt),
            }
            for price, snapshot in deduped_rows
        ],
    }
