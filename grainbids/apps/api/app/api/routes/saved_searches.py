from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.saved_search import SavedSearch
from app.models.source import Source
from app.services.market_canonicalization import canonical_key, canonical_commodity_name, canonical_location_name, canonical_source_name
from app.services.market_search_filters import apply_market_search_filters


router = APIRouter(prefix="/api/saved-searches", tags=["saved-searches"])


@router.get("")
def list_saved_searches(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(SavedSearch).where(SavedSearch.org_id == context.org_id).order_by(desc(SavedSearch.updated_at))
    ).scalars().all()
    return {"rows": [_serialize_saved_search(row) for row in rows]}


@router.get("/{saved_search_id}/preview")
def preview_saved_search(
    saved_search_id: uuid.UUID,
    limit: int = Query(60, ge=1, le=300),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(SavedSearch).where(SavedSearch.id == saved_search_id, SavedSearch.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="saved search not found")

    query: Select = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .order_by(PriceSnapshot.captured_at.desc(), NormalizedPrice.location.asc())
    )
    query = _apply_saved_search_filters(query, row)
    rows = db.execute(query.limit(limit)).all()
    return {
        "saved_search": _serialize_saved_search(row),
        "rows": [
            {
                "id": str(price.id),
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": canonical_location_name(price.location) or "-",
                "source_name": canonical_source_name(price.source_name),
                "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
                "delivery_label": price.delivery_label or price.delivery_end or price.delivery_start,
                "futures_month": price.futures_month,
                "futures_price": float(price.futures_price) if price.futures_price is not None else None,
                "basis": float(price.basis) if price.basis is not None else None,
                "cash_price_bu": float(price.cash_price_bu) if price.cash_price_bu is not None else None,
                "cash_price_mt": float(price.cash_price_mt) if price.cash_price_mt is not None else None,
            }
            for price, snapshot in rows
        ],
    }


@router.post("")
def create_saved_search(
    name: str = Query(..., min_length=2, max_length=200),
    commodity_name: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    region: str | None = Query(None),
    delivery_months: str | None = Query(None, description="Comma-separated month labels"),
    target_cash_price_bu: float | None = Query(None),
    target_basis: float | None = Query(None),
    is_active: bool = Query(True),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = _build_filters_json(
        commodity_name=commodity_name,
        location=location,
        source_name=source_name,
        location_id=location_id,
        company_id=company_id,
        region=region,
    )
    row = SavedSearch(
        org_id=context.org_id,
        name=name.strip(),
        filters_json=filters,
        delivery_months_json=_parse_csv_values(delivery_months),
        target_cash_price_bu=target_cash_price_bu,
        target_basis=target_basis,
        is_active=is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_saved_search(row)


@router.patch("/{saved_search_id}")
def update_saved_search(
    saved_search_id: uuid.UUID,
    name: str | None = Query(None, min_length=2, max_length=200),
    commodity_name: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    region: str | None = Query(None),
    delivery_months: str | None = Query(None, description="Comma-separated month labels"),
    target_cash_price_bu: float | None = Query(None),
    target_basis: float | None = Query(None),
    is_active: bool | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(SavedSearch).where(SavedSearch.id == saved_search_id, SavedSearch.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="saved search not found")

    if name is not None:
        row.name = name.strip()
    if is_active is not None:
        row.is_active = is_active
    if target_cash_price_bu is not None:
        row.target_cash_price_bu = target_cash_price_bu
    if target_basis is not None:
        row.target_basis = target_basis
    if delivery_months is not None:
        row.delivery_months_json = _parse_csv_values(delivery_months)

    filters = dict(row.filters_json or {})
    _merge_filter(filters, "commodity_name", commodity_name)
    _merge_filter(filters, "location", location)
    _merge_filter(filters, "source_name", source_name)
    _merge_filter(filters, "region", region)
    _merge_uuid_filter(filters, "location_id", location_id)
    _merge_uuid_filter(filters, "company_id", company_id)
    row.filters_json = filters

    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_saved_search(row)


@router.delete("/{saved_search_id}")
def delete_saved_search(
    saved_search_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(SavedSearch).where(SavedSearch.id == saved_search_id, SavedSearch.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    db.delete(row)
    db.commit()
    return {"deleted": str(saved_search_id)}


def _serialize_saved_search(row: SavedSearch) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "filters_json": row.filters_json or {},
        "delivery_months": row.delivery_months_json or [],
        "target_cash_price_bu": float(row.target_cash_price_bu) if row.target_cash_price_bu is not None else None,
        "target_basis": float(row.target_basis) if row.target_basis is not None else None,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _build_filters_json(
    *,
    commodity_name: str | None,
    location: str | None,
    source_name: str | None,
    location_id: uuid.UUID | None,
    company_id: uuid.UUID | None,
    region: str | None,
) -> dict:
    filters: dict[str, str] = {}
    _merge_filter(filters, "commodity_name", commodity_name)
    _merge_filter(filters, "location", location)
    _merge_filter(filters, "source_name", source_name)
    _merge_filter(filters, "region", region)
    _merge_uuid_filter(filters, "location_id", location_id)
    _merge_uuid_filter(filters, "company_id", company_id)
    return filters


def _merge_filter(filters: dict[str, str], key: str, value: str | None) -> None:
    if value is None:
        return
    stripped = value.strip()
    if not stripped:
        filters.pop(key, None)
        return
    filters[key] = stripped


def _merge_uuid_filter(filters: dict[str, str], key: str, value: uuid.UUID | None) -> None:
    if value is None:
        return
    filters[key] = str(value)


def _parse_csv_values(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    parsed = [token.strip() for token in raw.split(",")]
    values: list[str] = []
    seen: set[str] = set()
    for token in parsed:
        if not token:
            continue
        key = canonical_key(token)
        if not key or key in seen:
            continue
        seen.add(key)
        values.append(token)
    return values or None


def _apply_saved_search_filters(query: Select, row: SavedSearch) -> Select:
    return apply_market_search_filters(query, filters=row.filters_json or {}, delivery_months=row.delivery_months_json or [])
