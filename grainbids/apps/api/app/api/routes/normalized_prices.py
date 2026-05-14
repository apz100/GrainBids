from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, and_, case, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.company import Company
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import (
    canonical_commodity_name,
    canonical_key,
    canonical_location_name,
    canonical_source_name,
    normalize_text,
    source_scope,
)


router = APIRouter(prefix="/api/normalized-prices", tags=["normalized-prices"])


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
    # Some legacy rows were loaded as cents-per-bu (140) instead of dollars (1.40).
    if abs(number) >= 10:
        return number / 100.0
    return number
def _build_filters(
    commodity: str | None,
    location: str | None,
    source_name: str | None,
    region: str | None,
    captured_date: date | None,
    company_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
):
    filters = []

    if commodity:
        filters.append(NormalizedPrice.commodity_name.ilike(f"%{commodity.strip()}%"))
    if location:
        filters.append(NormalizedPrice.location.ilike(f"%{location.strip()}%"))
    if source_name:
        filters.append(NormalizedPrice.source_name.ilike(f"%{source_name.strip()}%"))
    if region:
        filters.append(NormalizedPrice.source_name.ilike(f"%{region.strip()}%"))
    if company_id:
        filters.append(NormalizedPrice.company_id == company_id)
    if location_id:
        filters.append(NormalizedPrice.location_id == location_id)
    if captured_date:
        start_dt = datetime.combine(captured_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(captured_date, time.max, tzinfo=timezone.utc)
        filters.append(and_(PriceSnapshot.captured_at >= start_dt, PriceSnapshot.captured_at <= end_dt))

    return filters


def _build_quality_filters() -> list:
    has_futures_month = func.length(func.trim(func.coalesce(NormalizedPrice.futures_month, ""))) > 0
    has_delivery_window = or_(
        func.length(func.trim(func.coalesce(NormalizedPrice.delivery_end, ""))) > 0,
        func.length(func.trim(func.coalesce(NormalizedPrice.delivery_label, ""))) > 0,
    )
    return [
        has_delivery_window,
        has_futures_month,
        NormalizedPrice.futures_price.is_not(None),
        NormalizedPrice.basis.is_not(None),
        NormalizedPrice.cash_price_bu.is_not(None),
        NormalizedPrice.cash_price_mt.is_not(None),
    ]


def _base_query(context: RequestContext) -> Select:
    return (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
    )


def _with_sorting(query: Select, sort: str) -> Select:
    source_priority = case(
        (Source.source_type == "automated", 0),
        (Source.source_type == "file", 1),
        else_=2,
    )
    if sort == "basis_desc":
        return query.order_by(desc(NormalizedPrice.basis), source_priority.asc(), desc(PriceSnapshot.captured_at))
    if sort == "basis_asc":
        return query.order_by(NormalizedPrice.basis.asc(), source_priority.asc(), desc(PriceSnapshot.captured_at))
    if sort == "cash_bu_desc":
        return query.order_by(desc(NormalizedPrice.cash_price_bu), source_priority.asc(), desc(PriceSnapshot.captured_at))
    if sort == "cash_bu_asc":
        return query.order_by(NormalizedPrice.cash_price_bu.asc(), source_priority.asc(), desc(PriceSnapshot.captured_at))
    if sort == "basis_change_desc":
        return query.order_by(desc(func.abs(NormalizedPrice.basis_change)), source_priority.asc(), desc(PriceSnapshot.captured_at))
    return query.order_by(source_priority.asc(), desc(PriceSnapshot.captured_at), NormalizedPrice.location, NormalizedPrice.commodity_name)


@router.get("")
def list_normalized_prices(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    region: str | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    captured_date: date | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    query: Select = _base_query(context).order_by(desc(PriceSnapshot.captured_at), NormalizedPrice.location)

    filters = _build_filters(
        commodity=commodity,
        location=location,
        source_name=source_name,
        region=region,
        captured_date=captured_date,
        company_id=company_id,
        location_id=location_id,
    )
    if filters:
        query = query.where(*filters)

    rows = db.execute(query.limit(limit)).all()

    return {
        "rows": [
            {
                "id": str(price.id),
                "snapshot_id": str(price.snapshot_id),
                "company_id": str(price.company_id) if price.company_id else None,
                "location_id": str(price.location_id) if price.location_id else None,
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": canonical_location_name(price.location) or "-",
                "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
                "source_name": canonical_source_name(price.source_name),
                "delivery_start": normalize_text(price.delivery_start),
                "delivery_end": normalize_text(price.delivery_end),
                "delivery_label": normalize_text(price.delivery_label),
                "futures_month": normalize_text(price.futures_month),
                "futures_price": _to_float(price.futures_price),
                "basis": _to_basis_float(price.basis),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_mt": _to_float(price.cash_price_mt),
                "basis_change": _to_basis_float(price.basis_change),
                "cash_price_bu_change": _to_float(price.cash_price_bu_change),
                "cash_price_mt_change": _to_float(price.cash_price_mt_change),
                "composite_key": price.composite_key,
            }
            for price, snapshot in rows
        ]
    }


@router.get("/facets")
def facets(
    captured_date: date | None = Query(None),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    filters = _build_filters(
        commodity=None,
        location=None,
        source_name=None,
        region=None,
        captured_date=captured_date,
    )
    quality_filters = _build_quality_filters()
    commodity_query = (
        select(func.distinct(NormalizedPrice.commodity_name))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
    )
    location_query = (
        select(func.distinct(NormalizedPrice.location))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
    )
    source_query = (
        select(func.distinct(NormalizedPrice.source_name))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
    )
    if filters:
        commodity_query = commodity_query.where(*filters)
        location_query = location_query.where(*filters)
        source_query = source_query.where(*filters)
    commodity_query = commodity_query.where(*quality_filters)
    location_query = location_query.where(*quality_filters)
    source_query = source_query.where(*quality_filters)

    commodity_map: dict[str, str] = {}
    for value in db.execute(commodity_query).scalars().all():
        normalized = canonical_commodity_name(value)
        key = canonical_key(normalized)
        if key and normalized and key not in commodity_map:
            commodity_map[key] = normalized

    location_map: dict[str, str] = {}
    for value in db.execute(location_query).scalars().all():
        normalized = canonical_location_name(value)
        key = canonical_key(normalized)
        if key and normalized and key not in location_map:
            location_map[key] = normalized

    company_map: dict[str, str] = {}
    region_map: dict[str, str] = {}
    for value in db.execute(source_query).scalars().all():
        scope, label = source_scope(value)
        key = canonical_key(label)
        if not key or not label:
            continue
        if scope == "region":
            if key not in region_map:
                region_map[key] = label
        else:
            if key not in company_map:
                company_map[key] = label

    company_rows_query = (
        select(Company.id, Company.name)
        .join(NormalizedPrice, NormalizedPrice.company_id == Company.id)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .distinct()
        .order_by(Company.name.asc())
    )
    location_rows_query = (
        select(Location.id, Location.name, Location.region)
        .join(NormalizedPrice, NormalizedPrice.location_id == Location.id)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .distinct()
        .order_by(Location.name.asc())
    )
    if filters:
        company_rows_query = company_rows_query.where(*filters)
        location_rows_query = location_rows_query.where(*filters)
    company_rows_query = company_rows_query.where(*quality_filters)
    location_rows_query = location_rows_query.where(*quality_filters)

    company_rows = db.execute(company_rows_query).all()
    location_rows = db.execute(location_rows_query).all()

    deduped_companies: dict[str, dict[str, str]] = {}
    for company_id, name in company_rows:
        display_name = canonical_source_name(name) or (name or "").strip()
        key = canonical_key(display_name)
        if not key or not display_name:
            continue
        if key not in deduped_companies:
            deduped_companies[key] = {"id": str(company_id), "name": display_name}

    deduped_locations: dict[str, dict[str, str | None]] = {}
    for location_id, name, region in location_rows:
        display_name = canonical_location_name(name) or (name or "").strip()
        key = canonical_key(display_name)
        if not key or not display_name:
            continue
        if key not in deduped_locations:
            deduped_locations[key] = {
                "id": str(location_id),
                "name": display_name,
                "region": normalize_text(region),
            }

    return {
        "commodities": sorted(commodity_map.values()),
        "locations": sorted(location_map.values()),
        "source_names": sorted([*company_map.values(), *region_map.values()]),
        "company_names": sorted(company_map.values()),
        "region_names": sorted(region_map.values()),
        "company_rows": sorted(deduped_companies.values(), key=lambda row: row["name"]),
        "location_rows": sorted(deduped_locations.values(), key=lambda row: row["name"]),
    }


@router.get("/preview")
def preview(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    region: str | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    captured_date: date | None = Query(None),
    sort: str = Query(
        "captured_desc",
        pattern="^(captured_desc|basis_desc|basis_asc|cash_bu_desc|cash_bu_asc|basis_change_desc)$",
    ),
    limit: int = Query(80, ge=1, le=250),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    filters = _build_filters(
        commodity=commodity,
        location=location,
        source_name=source_name,
        region=region,
        captured_date=captured_date,
        company_id=company_id,
        location_id=location_id,
    )
    query: Select = _base_query(context)
    if filters:
        query = query.where(*filters)
    query = query.where(*_build_quality_filters())
    query = _with_sorting(query, sort)

    rows = db.execute(query.limit(limit * 3)).all()
    deduped_rows: list[tuple[NormalizedPrice, PriceSnapshot]] = []
    seen: set[str] = set()
    for price, snapshot in rows:
        location_key = str(price.location_id) if price.location_id else (canonical_key(price.location) or "-")
        company_key = str(price.company_id) if price.company_id else (canonical_key(canonical_source_name(price.source_name)) or "-")
        commodity_key = canonical_key(price.commodity_name) or "-"
        delivery_key = canonical_key(price.delivery_label or price.delivery_end or price.delivery_start) or "-"
        futures_key = canonical_key(price.futures_month) or "-"
        dedupe_key = "|".join([location_key, company_key, commodity_key, delivery_key, futures_key])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped_rows.append((price, snapshot))
        if len(deduped_rows) >= limit:
            break

    return {
        "rows": [
            {
                "id": str(price.id),
                "company_id": str(price.company_id) if price.company_id else None,
                "location_id": str(price.location_id) if price.location_id else None,
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": canonical_location_name(price.location) or "-",
                "source_name": canonical_source_name(price.source_name),
                "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
                "delivery_label": normalize_text(price.delivery_label) or normalize_text(price.delivery_end),
                "futures_month": normalize_text(price.futures_month),
                "futures_price": _to_float(price.futures_price),
                "basis": _to_basis_float(price.basis),
                "basis_change": _to_basis_float(price.basis_change),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_bu_change": _to_float(price.cash_price_bu_change),
                "cash_price_mt": _to_float(price.cash_price_mt),
                "cash_price_mt_change": _to_float(price.cash_price_mt_change),
                "composite_key": price.composite_key,
            }
            for price, snapshot in deduped_rows
        ]
    }


@router.get("/top-movers")
def top_movers(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    region: str | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    captured_date: date | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    query: Select = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .where(NormalizedPrice.basis_change.is_not(None))
        .order_by(desc(func.abs(NormalizedPrice.basis_change)), desc(PriceSnapshot.captured_at))
    )

    filters = _build_filters(
        commodity=commodity,
        location=location,
        source_name=source_name,
        region=region,
        captured_date=captured_date,
        company_id=company_id,
        location_id=location_id,
    )
    if filters:
        query = query.where(*filters)
    query = query.where(*_build_quality_filters())

    rows = db.execute(query.limit(limit)).all()

    return {
        "rows": [
            {
                "id": str(price.id),
                "snapshot_id": str(price.snapshot_id),
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": canonical_location_name(price.location) or "-",
                "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
                "source_name": canonical_source_name(price.source_name),
                "basis": _to_basis_float(price.basis),
                "basis_change": _to_basis_float(price.basis_change),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_bu_change": _to_float(price.cash_price_bu_change),
                "cash_price_mt": _to_float(price.cash_price_mt),
                "cash_price_mt_change": _to_float(price.cash_price_mt_change),
            }
            for price, snapshot in rows
        ]
    }


@router.get("/summary")
def summary(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    region: str | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    captured_date: date | None = Query(None),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    filters = _build_filters(
        commodity=commodity,
        location=location,
        source_name=source_name,
        region=region,
        captured_date=captured_date,
        company_id=company_id,
        location_id=location_id,
    )

    normalized_basis_expr = case(
        (func.abs(NormalizedPrice.basis) >= 10, NormalizedPrice.basis / 100),
        else_=NormalizedPrice.basis,
    )
    basis_query = (
        select(func.avg(normalized_basis_expr), func.count(NormalizedPrice.id))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
    )
    if filters:
        basis_query = basis_query.where(*filters)

    avg_basis, row_count = db.execute(basis_query).one()

    active_alert_rules = db.execute(
        select(func.count(AlertRule.id)).where(AlertRule.org_id == context.org_id, AlertRule.is_active.is_(True))
    ).scalar_one()

    open_alerts = db.execute(
        select(func.count(Alert.id))
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(AlertRule.org_id == context.org_id, Alert.status.in_(["new", "open", "pending"]))
    ).scalar_one()

    return {
        "average_basis": _to_float(avg_basis),
        "row_count": int(row_count or 0),
        "active_alert_rules": int(active_alert_rules or 0),
        "open_alerts": int(open_alerts or 0),
    }
