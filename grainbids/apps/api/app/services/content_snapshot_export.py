from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import math
from typing import Iterable
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes.normalized_prices import _snapshot_freshness_filters, _user_visible_market_filters
from app.models.company import Company
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source


CONTENT_SNAPSHOT_SCHEMA_VERSION = "grainbids.content-snapshot.v1"
DEFAULT_COMMODITIES = ("Corn", "Soybeans", "Wheat")


def build_content_snapshot(
    db: Session,
    *,
    org_id: uuid.UUID,
    region: str | None,
    commodities: Iterable[str] | None,
    limit: int,
    currency_code: str,
    max_age_minutes: int,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    generated_at = _aware_datetime(generated_at or datetime.now(timezone.utc))
    normalized_commodities = _normalize_commodities(commodities)
    normalized_region = (region or "").strip() or None

    query = (
        select(NormalizedPrice, PriceSnapshot, Source, Company, Location)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .outerjoin(Company, Company.id == NormalizedPrice.company_id)
        .outerjoin(Location, Location.id == NormalizedPrice.location_id)
        .where(
            Source.org_id == org_id,
            NormalizedPrice.commodity_name.in_(normalized_commodities),
            *_user_visible_market_filters(include_non_canonical=False),
            *_snapshot_freshness_filters(enforce_latest=True),
        )
    )
    if normalized_region:
        region_pattern = f"%{normalized_region}%"
        query = query.where(
            or_(
                Location.region.ilike(region_pattern),
                Source.region.ilike(region_pattern),
            )
        )

    query = query.order_by(
        PriceSnapshot.captured_at.desc(),
        NormalizedPrice.commodity_name.asc(),
        func.coalesce(Location.name, NormalizedPrice.location).asc(),
        func.coalesce(Company.name, NormalizedPrice.source_name, Source.name).asc(),
        NormalizedPrice.delivery_end.asc(),
        NormalizedPrice.futures_month.asc(),
        NormalizedPrice.id.asc(),
    )
    result_rows = db.execute(query.limit(limit + 1)).all()
    truncated = len(result_rows) > limit
    result_rows = result_rows[:limit]

    rows = [
        _serialize_content_row(
            price=price,
            snapshot=snapshot,
            source=source,
            company=company,
            location=location,
            currency_code=currency_code,
        )
        for price, snapshot, source, company, location in result_rows
    ]
    captured_values = [value for row in rows if (value := _parse_datetime(row["captured_at"])) is not None]
    data_as_of = max(captured_values) if captured_values else None
    age_minutes = None
    if data_as_of is not None:
        age_minutes = max(0.0, (generated_at - data_as_of).total_seconds() / 60.0)
    freshness_status = (
        "empty"
        if data_as_of is None
        else "stale"
        if age_minutes is not None and age_minutes > max_age_minutes
        else "fresh"
    )

    fingerprint_payload = {
        "schema_version": CONTENT_SNAPSHOT_SCHEMA_VERSION,
        "org_id": str(org_id),
        "region": normalized_region,
        "commodities": list(normalized_commodities),
        "rows": rows,
    }
    snapshot_id = "sha256:" + sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": CONTENT_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "generated_at": generated_at.isoformat(),
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "filters": {
            "region": normalized_region,
            "commodities": list(normalized_commodities),
            "canonical_only": True,
            "latest_source_snapshot_only": True,
        },
        "freshness": {
            "status": freshness_status,
            "max_age_minutes": max_age_minutes,
            "age_minutes": round(age_minutes, 3) if age_minutes is not None else None,
        },
        "row_count": len(rows),
        "truncated": truncated,
        "rows": rows,
    }


def _serialize_content_row(
    *,
    price: NormalizedPrice,
    snapshot: PriceSnapshot,
    source: Source,
    company: Company | None,
    location: Location | None,
    currency_code: str,
) -> dict[str, object]:
    facility_name = (location.name if location is not None else None) or price.location
    buyer_name = (company.name if company is not None else None) or price.source_name or source.name
    normalized_currency = currency_code.strip().upper() or "CAD"
    return {
        "id": str(price.id),
        "snapshot_id": str(snapshot.id),
        "source_id": str(source.id),
        "source_name": source.name,
        "source_url": source.url,
        "source_type": source.source_type,
        "source_region": source.region,
        "source_confidence": _number(source.confidence_score),
        "source_last_success_at": (
            _aware_datetime(source.last_success_at).isoformat() if source.last_success_at is not None else None
        ),
        "source_consecutive_failures": int(source.consecutive_failures or 0),
        "company_id": str(company.id) if company is not None else None,
        "company_name": company.name if company is not None else None,
        "facility_id": str(location.id) if location is not None else None,
        "facility_name": facility_name,
        "facility_region": location.region if location is not None else source.region,
        "facility_postal_code": location.postal_code if location is not None else None,
        "facility_latitude": _number(location.latitude) if location is not None else None,
        "facility_longitude": _number(location.longitude) if location is not None else None,
        "buyer_name": buyer_name,
        "captured_at": _aware_datetime(snapshot.captured_at).isoformat(),
        "commodity": price.commodity_name,
        "location": facility_name,
        "delivery_label": price.delivery_label,
        "delivery_start": price.delivery_start,
        "delivery_end": price.delivery_end,
        "futures_month": price.futures_month,
        "futures_price": _number(price.futures_price),
        "futures_change": _number(price.futures_change),
        "basis": _basis_number(price.basis),
        "basis_change": _basis_number(price.basis_change),
        "basis_change_strict": _basis_number(price.basis_change_strict),
        "cash_price_bu": _number(price.cash_price_bu),
        "cash_price_mt": _number(price.cash_price_mt),
        "cash_price_bu_change": _number(price.cash_price_bu_change),
        "cash_price_mt_change": _number(price.cash_price_mt_change),
        "currency_code": normalized_currency,
        "cash_price_bu_unit": f"{normalized_currency}/bu",
        "cash_price_mt_unit": f"{normalized_currency}/MT",
        "basis_unit": f"{normalized_currency}/bu",
        "is_canonical": bool(price.is_canonical),
        "canonical_rank": price.canonical_rank,
        "canonical_reason": price.canonical_reason,
    }


def _normalize_commodities(values: Iterable[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values or DEFAULT_COMMODITIES:
        item = str(value).strip()
        if item and item not in normalized:
            normalized.append(item)
    if not normalized:
        raise ValueError("At least one commodity is required")
    return tuple(normalized)


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _basis_number(value: object) -> float | None:
    number = _number(value)
    if number is not None and abs(number) >= 10:
        return number / 100.0
    return number


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_datetime(value)
    if isinstance(value, str) and value:
        try:
            return _aware_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
