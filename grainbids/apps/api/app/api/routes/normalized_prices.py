from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, and_, desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot


router = APIRouter(prefix="/api/normalized-prices", tags=["normalized-prices"])


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _build_filters(
    commodity: str | None,
    location: str | None,
    source_name: str | None,
    captured_date: date | None,
):
    filters = []

    if commodity:
        filters.append(NormalizedPrice.commodity_name.ilike(f"%{commodity.strip()}%"))
    if location:
        filters.append(NormalizedPrice.location.ilike(f"%{location.strip()}%"))
    if source_name:
        filters.append(NormalizedPrice.source_name.ilike(f"%{source_name.strip()}%"))
    if captured_date:
        start_dt = datetime.combine(captured_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(captured_date, time.max, tzinfo=timezone.utc)
        filters.append(and_(PriceSnapshot.captured_at >= start_dt, PriceSnapshot.captured_at <= end_dt))

    return filters


@router.get("")
def list_normalized_prices(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    captured_date: date | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query: Select = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .order_by(desc(PriceSnapshot.captured_at), NormalizedPrice.location)
    )

    filters = _build_filters(commodity=commodity, location=location, source_name=source_name, captured_date=captured_date)
    if filters:
        query = query.where(*filters)

    rows = db.execute(query.limit(limit)).all()

    return {
        "rows": [
            {
                "id": str(price.id),
                "snapshot_id": str(price.snapshot_id),
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": price.location,
                "commodity_name": price.commodity_name,
                "source_name": price.source_name,
                "delivery_start": price.delivery_start,
                "delivery_end": price.delivery_end,
                "delivery_label": price.delivery_label,
                "futures_month": price.futures_month,
                "futures_price": _to_float(price.futures_price),
                "basis": _to_float(price.basis),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_mt": _to_float(price.cash_price_mt),
                "basis_change": _to_float(price.basis_change),
                "composite_key": price.composite_key,
            }
            for price, snapshot in rows
        ]
    }


@router.get("/top-movers")
def top_movers(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    captured_date: date | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query: Select = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .where(NormalizedPrice.basis_change.is_not(None))
        .order_by(desc(func.abs(NormalizedPrice.basis_change)), desc(PriceSnapshot.captured_at))
    )

    filters = _build_filters(commodity=commodity, location=location, source_name=source_name, captured_date=captured_date)
    if filters:
        query = query.where(*filters)

    rows = db.execute(query.limit(limit)).all()

    return {
        "rows": [
            {
                "id": str(price.id),
                "snapshot_id": str(price.snapshot_id),
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": price.location,
                "commodity_name": price.commodity_name,
                "source_name": price.source_name,
                "basis": _to_float(price.basis),
                "basis_change": _to_float(price.basis_change),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_mt": _to_float(price.cash_price_mt),
            }
            for price, snapshot in rows
        ]
    }


@router.get("/summary")
def summary(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    captured_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    filters = _build_filters(commodity=commodity, location=location, source_name=source_name, captured_date=captured_date)

    basis_query = (
        select(func.avg(NormalizedPrice.basis), func.count(NormalizedPrice.id))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
    )
    if filters:
        basis_query = basis_query.where(*filters)

    avg_basis, row_count = db.execute(basis_query).one()

    active_alert_rules = db.execute(
        select(func.count(AlertRule.id)).where(AlertRule.is_active.is_(True))
    ).scalar_one()

    open_alerts = db.execute(
        select(func.count(Alert.id)).where(Alert.status.in_(["new", "open", "pending"]))
    ).scalar_one()

    return {
        "average_basis": _to_float(avg_basis),
        "row_count": int(row_count or 0),
        "active_alert_rules": int(active_alert_rules or 0),
        "open_alerts": int(open_alerts or 0),
    }
