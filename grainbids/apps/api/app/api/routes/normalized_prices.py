from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
import math
import re
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, String, and_, case, cast, desc, false, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.company import Company
from app.models.ingestion_run import IngestionRun
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
    region_source_names,
    source_scope,
)


router = APIRouter(prefix="/api/normalized-prices", tags=["normalized-prices"])
QUALITY_SCORE_FIELDS = 7.0
LOCATION_COMPANY_DISPLAY_OVERRIDES = {
    "prescott": "Port of Prescott",
    "cardinal": "Ingredion",
    "johnstown": "Greenfield Global",
    "embrun": "Embrun Co-op (GLG)",
    "embrun co-op": "Embrun Co-op (GLG)",
}


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


def _coalesce_zero(value: float | None) -> float:
    return 0.0 if value is None else value


def _quality_score_expr():
    delivery_present = func.coalesce(NormalizedPrice.delivery_end, NormalizedPrice.delivery_label, NormalizedPrice.delivery_start).is_not(None)
    invalid_labels = tuple(settings.invalid_commodity_labels_set) or ("__invalid_commodity__",)
    commodity_valid = func.lower(func.trim(NormalizedPrice.commodity_name)).not_in(invalid_labels)
    return (
        case((commodity_valid, 1), else_=0)
        + case((NormalizedPrice.futures_month.is_not(None), 1), else_=0)
        + case((NormalizedPrice.futures_price.is_not(None), 1), else_=0)
        + case((NormalizedPrice.basis.is_not(None), 1), else_=0)
        + case((NormalizedPrice.cash_price_bu.is_not(None), 1), else_=0)
        + case((NormalizedPrice.cash_price_mt.is_not(None), 1), else_=0)
        + case((delivery_present, 1), else_=0)
    ) / QUALITY_SCORE_FIELDS


def _canonical_and_quality_filters(include_non_canonical: bool):
    invalid_labels = tuple(settings.invalid_commodity_labels_set) or ("__invalid_commodity__",)
    filters = [func.lower(func.trim(NormalizedPrice.commodity_name)).not_in(invalid_labels)]
    if not include_non_canonical:
        filters.append(NormalizedPrice.is_canonical.is_(True))
    filters.append(_quality_score_expr() >= settings.canonical_min_quality_score)
    return filters


def _user_visible_market_filters(include_non_canonical: bool):
    return [
        *_canonical_and_quality_filters(include_non_canonical),
        *_build_quality_filters(),
        *_build_market_period_recency_filters(),
    ]


def _staleness_month_key(value: str | None) -> int | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    lowered = normalized.casefold()
    if "crop" in lowered or "harvest" in lowered:
        return None
    key = _month_sort_key_value(normalized)
    if key is None:
        return None
    # Month-only labels without year (for example "May") are intentionally
    # treated as unspecified and should not be filtered as stale.
    if key >= 9999 * 12:
        return None
    return key


def _is_expired_market_period(price: NormalizedPrice) -> bool:
    current_key = (date.today().year * 12) + date.today().month
    delivery_value = normalize_text(price.delivery_label) or normalize_text(price.delivery_end) or normalize_text(price.delivery_start)
    delivery_key = _staleness_month_key(delivery_value)
    if delivery_key is not None and delivery_key < current_key:
        return True
    futures_key = _staleness_month_key(normalize_text(price.futures_month))
    if futures_key is not None and futures_key < current_key:
        return True
    return False


def _build_market_period_recency_filters() -> list:
    # Prevent stale month/year market periods (for example, April delivery / May futures)
    # from surfacing in user-facing tables after contracts roll forward.
    period_pattern = (
        r"(?i)^(january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\s+\d{4}$"
    )
    delivery_value = func.trim(
        func.coalesce(
            NormalizedPrice.delivery_label,
            NormalizedPrice.delivery_end,
            NormalizedPrice.delivery_start,
            "",
        )
    )
    futures_value = func.trim(func.coalesce(NormalizedPrice.futures_month, ""))
    delivery_month = case(
        (delivery_value.op("~")(period_pattern), func.to_date(func.initcap(delivery_value), "Month YYYY")),
        else_=None,
    )
    futures_month = case(
        (futures_value.op("~")(period_pattern), func.to_date(func.initcap(futures_value), "Month YYYY")),
        else_=None,
    )
    current_month_start = date.today().replace(day=1)
    return [
        or_(delivery_month.is_(None), delivery_month >= current_month_start),
        or_(futures_month.is_(None), futures_month >= current_month_start),
    ]


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
        source_filter_values = _canonical_source_filter_values(source_name)
        if source_filter_values:
            filters.append(func.lower(func.trim(func.coalesce(NormalizedPrice.source_name, ""))).in_(source_filter_values))
    if region:
        region_filter_values = [value.casefold() for value in region_source_names(region)]
        if region_filter_values:
            filters.append(func.lower(func.trim(func.coalesce(NormalizedPrice.source_name, ""))).in_(region_filter_values))
        else:
            filters.append(false())
    if company_id:
        filters.append(NormalizedPrice.company_id == company_id)
    if location_id:
        filters.append(NormalizedPrice.location_id == location_id)
    if captured_date:
        start_dt = datetime.combine(captured_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(captured_date, time.max, tzinfo=timezone.utc)
        filters.append(and_(PriceSnapshot.captured_at >= start_dt, PriceSnapshot.captured_at <= end_dt))

    return filters


def _canonical_source_filter_values(source_name: str | None) -> list[str]:
    normalized = normalize_text(source_name)
    if normalized is None:
        return []
    values: list[str] = []
    for candidate in (normalized, canonical_source_name(normalized)):
        key = canonical_key(candidate)
        if key and key not in values:
            values.append(key)
    return values


def _source_key(source_name: str | None) -> str | None:
    return canonical_key(canonical_source_name(source_name))


def _display_company_name(source_name: str | None) -> str | None:
    display_name = canonical_source_name(source_name)
    if display_name is None:
        return None
    scope, _label = source_scope(display_name)
    if scope == "region":
        return None
    source_key = canonical_key(display_name)
    if source_key is not None and source_key in settings.canonical_aggregator_sources_set:
        return None
    return display_name


def _source_attribution_name(source_name: str | None) -> str | None:
    display_name = canonical_source_name(source_name)
    if display_name is None:
        return None
    scope, _label = source_scope(display_name)
    source_key = canonical_key(display_name)
    if scope == "region":
        return display_name
    if source_key is not None and source_key in settings.canonical_aggregator_sources_set:
        return display_name
    return None


def _trusted_company_name(company_name: str | None) -> str | None:
    normalized = canonical_source_name(company_name)
    if normalized is None:
        return None
    scope, _label = source_scope(normalized)
    if scope == "region":
        return None
    key = canonical_key(normalized)
    if key is not None and key in settings.canonical_aggregator_sources_set:
        return None
    return normalized


def _display_company_name_for_row(
    price: NormalizedPrice,
    *,
    company_name_map: dict[uuid.UUID, str],
    location_company_map: dict[uuid.UUID, uuid.UUID] | None = None,
) -> str | None:
    location_key = canonical_key(canonical_location_name(price.location))
    if location_key is not None:
        override = LOCATION_COMPANY_DISPLAY_OVERRIDES.get(location_key)
        if override:
            return override
    if price.company_id is not None:
        trusted = _trusted_company_name(company_name_map.get(price.company_id))
        if trusted is not None:
            return trusted
    if location_company_map and price.location_id is not None:
        location_company_id = location_company_map.get(price.location_id)
        if location_company_id is not None:
            trusted = _trusted_company_name(company_name_map.get(location_company_id))
            if trusted is not None:
                return trusted
    source_display = _display_company_name(price.source_name)
    if source_display is not None:
        return source_display
    return None


def _load_company_name_map(
    db: Session,
    *,
    company_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not company_ids:
        return {}
    rows = db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids))).all()
    return {company_id: name for company_id, name in rows if company_id is not None and name}


def _load_company_display_identity_map(
    db: Session,
    *,
    org_id: uuid.UUID,
) -> dict[str, tuple[str, str]]:
    rows = db.execute(select(Company.id, Company.name).where(Company.org_id == org_id)).all()
    identities: dict[str, tuple[str, str]] = {}
    for company_id, raw_name in rows:
        display_name = canonical_source_name(raw_name) or normalize_text(raw_name)
        display_key = canonical_key(display_name)
        if not display_key or not display_name:
            continue
        if display_key not in identities:
            identities[display_key] = (str(company_id), display_name)
    return identities


def _load_location_company_map(
    db: Session,
    *,
    location_ids: set[uuid.UUID],
) -> dict[uuid.UUID, uuid.UUID]:
    if not location_ids:
        return {}
    rows = db.execute(select(Location.id, Location.company_id).where(Location.id.in_(location_ids))).all()
    return {
        location_id: company_id
        for location_id, company_id in rows
        if location_id is not None and company_id is not None
    }


def _market_period_dedupe_key(value: str | None) -> str:
    month_key = _month_sort_key_value(value)
    if month_key is not None:
        return f"month:{month_key}"
    return canonical_key(value) or "-"


def _preview_row_dedupe_key(
    price: NormalizedPrice,
    *,
    company_name_map: dict[uuid.UUID, str],
    location_company_map: dict[uuid.UUID, uuid.UUID],
) -> str:
    location_key = canonical_key(canonical_location_name(price.location)) or canonical_key(price.location) or "-"
    display_company_name = _display_company_name_for_row(
        price,
        company_name_map=company_name_map,
        location_company_map=location_company_map,
    )
    company_key = canonical_key(display_company_name) or "-"
    commodity_key = canonical_key(price.commodity_name) or "-"
    delivery_key = _market_period_dedupe_key(
        normalize_text(price.delivery_label)
        or normalize_text(price.delivery_end)
        or normalize_text(price.delivery_start)
        or normalize_text(price.futures_month)
    )
    futures_key = _market_period_dedupe_key(normalize_text(price.futures_month))
    return "|".join([location_key, company_key, commodity_key, delivery_key, futures_key])


def _serialize_preview_row(
    price: NormalizedPrice,
    snapshot: PriceSnapshot,
    candidate_counts: dict[str, int],
    company_name_map: dict[uuid.UUID, str],
    location_company_map: dict[uuid.UUID, uuid.UUID],
) -> dict[str, object]:
    company_name = _display_company_name_for_row(
        price,
        company_name_map=company_name_map,
        location_company_map=location_company_map,
    )
    basis_change = _to_basis_float(price.basis_change)
    futures_change = _to_float(getattr(price, "futures_change", None))
    cash_price_bu_change = _to_float(price.cash_price_bu_change)
    cash_price_mt_change = _to_float(price.cash_price_mt_change)
    source_attribution = _source_attribution_name(price.source_name)
    return {
        "id": str(price.id),
        "company_id": str(price.company_id) if price.company_id else None,
        "location_id": str(price.location_id) if price.location_id else None,
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        "location": canonical_location_name(price.location) or "-",
        "company_name": company_name,
        "source_name": canonical_source_name(price.source_name),
        "source_attribution": source_attribution,
        "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
        "delivery_label": _canonical_month_label(normalize_text(price.delivery_label) or normalize_text(price.delivery_end)),
        "futures_month": _canonical_month_label(normalize_text(price.futures_month)),
        "futures_price": _to_float(price.futures_price),
        "futures_change": futures_change if futures_change is not None else 0.0,
        "basis": _to_basis_float(price.basis),
        "basis_change": basis_change if basis_change is not None else 0.0,
        "basis_last_changed_at": price.basis_last_changed_at.isoformat() if price.basis_last_changed_at else None,
        "cash_price_bu": _to_float(price.cash_price_bu),
        "cash_price_bu_change": cash_price_bu_change if cash_price_bu_change is not None else 0.0,
        "cash_price_mt": _to_float(price.cash_price_mt),
        "cash_price_mt_change": cash_price_mt_change if cash_price_mt_change is not None else 0.0,
        "composite_key": price.composite_key,
        "candidate_count": candidate_counts.get(str(price.composite_key), 1),
        "selected_source_key": canonical_key(canonical_source_name(price.source_name)),
        "canonical_reason": price.canonical_reason,
        "is_canonical": price.is_canonical,
        "canonical_rank": price.canonical_rank,
    }


def _canonical_month_label(value: str | None) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    month_key = _month_sort_key_value(normalized)
    if month_key is None:
        return normalized
    year = (month_key - 1) // 12
    month = month_key - (year * 12)
    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    month_name = month_names.get(month)
    if month_name is None:
        return normalized
    if year >= 9999:
        return month_name
    return f"{month_name} {year}"


def _month_sort_key_value(value: str | None) -> int | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    label = normalized.casefold()
    month_map = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    month_tokens = "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december"
    # Month-day-year labels (e.g. "May 31, 2026") should sort as month/year.
    month_day_year_match = re.search(
        rf"\b({month_tokens})\b\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,\s*|\s+)(\d{{4}})\b",
        label,
    )
    if month_day_year_match:
        month = month_map.get(month_day_year_match.group(1))
        year = _parse_year_token(month_day_year_match.group(3))
        if month is not None and year is not None:
            return year * 12 + month

    # Month-year shorthand (e.g. May-26, Jul 2026). Exclude month-day-year where the
    # first number is day-of-month followed by comma and a full year.
    month_year_match = re.search(
        rf"\b({month_tokens})\b\s*([\-\/\s])\s*(\d{{2,4}})(?!\s*,\s*\d{{4}})\b",
        label,
    )
    if month_year_match:
        month = month_map.get(month_year_match.group(1))
        sep = month_year_match.group(2)
        year_token = month_year_match.group(3)
        year = _parse_year_token(year_token)
        try:
            raw_year = int(year_token)
        except (TypeError, ValueError):
            raw_year = None
        if month is not None and year is not None:
            # "May 31" is usually day-of-month (not year); keep it month-only.
            if not (sep.isspace() and raw_year is not None and len(str(year_token)) <= 2 and raw_year <= 31):
                return year * 12 + month

    harvest_match = re.search(r"\bharvest\b[^0-9]*(\d{2,4})?", label)
    if harvest_match:
        year = _parse_year_token(harvest_match.group(1))
        if year is not None:
            return year * 12 + 10

    futures_code_match = re.search(r"\b([fghjkmnquvxz])(?:c|s|w)?(\d{1,2})\b", label)
    if futures_code_match:
        code_to_month = {
            "f": 1,
            "g": 2,
            "h": 3,
            "j": 4,
            "k": 5,
            "m": 6,
            "n": 7,
            "q": 8,
            "u": 9,
            "v": 10,
            "x": 11,
            "z": 12,
        }
        month = code_to_month.get(futures_code_match.group(1))
        year = _parse_year_token(futures_code_match.group(2))
        if month is not None and year is not None:
            return year * 12 + month

    named_month_match = re.search(rf"\b({month_tokens})\b[^0-9]*(\d{{2,4}})?", label)
    if named_month_match:
        month = month_map.get(named_month_match.group(1))
        year_token = named_month_match.group(2)
        year = _parse_year_token(year_token)
        if month is not None and year is not None:
            # Avoid misreading month-day labels like "Nov 30" as year 2030.
            try:
                raw_year = int(year_token) if year_token is not None else None
            except (TypeError, ValueError):
                raw_year = None
            if raw_year is None or len(str(year_token)) == 4 or raw_year > 31:
                return year * 12 + month
        if month is not None:
            return 9999 * 12 + month
    return None


def _parse_year_token(token: str | None) -> int | None:
    if token is None:
        return None
    try:
        raw_year = int(token)
    except (TypeError, ValueError):
        return None
    return 2000 + raw_year if raw_year < 100 else raw_year


def _preview_group_sort_key(row: dict[str, object]) -> tuple[float, float, str]:
    cash_price_bu = row.get("cash_price_bu")
    basis = row.get("basis")
    location_name = str(row.get("location") or "")
    cash_value = float(cash_price_bu) if isinstance(cash_price_bu, (int, float)) else float("-inf")
    basis_value = float(basis) if isinstance(basis, (int, float)) else float("-inf")
    return (-cash_value, -basis_value, location_name.casefold())


def _group_preview_rows_by_delivery(
    rows: list[dict[str, object]],
    *,
    rows_per_group: int = 8,
) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        label = str(row.get("delivery_label") or row.get("futures_month") or "Unspecified")
        groups[label].append(row)

    output: list[dict[str, object]] = []
    sorted_labels = sorted(
        groups.keys(),
        key=lambda label: (
            _month_sort_key_value(label) is None,
            _month_sort_key_value(label) if _month_sort_key_value(label) is not None else 0,
        ),
    )
    for label in sorted_labels:
        grouped_rows = sorted(groups[label], key=_preview_group_sort_key)[:rows_per_group]
        top_cash_price_bu = None
        if grouped_rows:
            top_value = grouped_rows[0].get("cash_price_bu")
            if isinstance(top_value, (int, float)):
                top_cash_price_bu = float(top_value)
        output.append(
            {
                "label": label,
                "row_count": len(groups[label]),
                "top_cash_price_bu": top_cash_price_bu,
                "rows": grouped_rows,
            }
        )
    return output


def _prune_facet_rows(
    rows: list[dict[str, object]],
    *,
    minimum_market_count: int,
) -> list[dict[str, object]]:
    if minimum_market_count <= 1:
        return rows
    return [row for row in rows if int(row.get("market_count") or 0) >= minimum_market_count]


def _append_forced_company_rows(
    rows: list[dict[str, object]],
    *,
    all_company_rows_by_key: dict[str, dict[str, object]],
    forced_company_names: set[str],
) -> list[dict[str, object]]:
    merged = list(rows)
    present_keys = {
        key
        for key in (
            canonical_key(str(row.get("name") or ""))
            for row in rows
        )
        if key
    }
    for company_name in forced_company_names:
        key = canonical_key(company_name)
        if not key or key in present_keys:
            continue
        forced_row = all_company_rows_by_key.get(key)
        if forced_row is None:
            continue
        if int(forced_row.get("market_count") or 0) <= 0:
            continue
        merged.append(forced_row)
        present_keys.add(key)
    return merged


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


def _snapshot_freshness_filters(*, enforce_latest: bool) -> list:
    if not enforce_latest:
        return []

    # File-ingestion sources can emit many snapshots per run (one per commodity chunk).
    # Keep rows from the latest completed run for that source to avoid leaking stale markets
    # that disappeared from the newest run (for example, expired delivery/futures combinations).
    latest_completed_run_id = (
        select(IngestionRun.id)
        .where(
            IngestionRun.source_name == Source.name,
            IngestionRun.status == "completed",
        )
        .order_by(desc(func.coalesce(IngestionRun.completed_at, IngestionRun.started_at)), desc(IngestionRun.started_at), desc(IngestionRun.id))
        .limit(1)
        .scalar_subquery()
    )
    snapshot_alias = aliased(PriceSnapshot)
    latest_snapshot_id = (
        select(snapshot_alias.id)
        .where(snapshot_alias.source_id == Source.id)
        .order_by(desc(snapshot_alias.captured_at), desc(snapshot_alias.id))
        .limit(1)
        .scalar_subquery()
    )
    run_id_text = PriceSnapshot.raw_payload_json["ingestion_run_id"].astext
    return [
        or_(
            and_(run_id_text.is_not(None), run_id_text == cast(latest_completed_run_id, String)),
            and_(run_id_text.is_(None), PriceSnapshot.id == latest_snapshot_id),
        )
    ]


def _base_query(context: RequestContext, *, enforce_latest: bool) -> Select:
    query = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
    )
    freshness_filters = _snapshot_freshness_filters(enforce_latest=enforce_latest)
    if freshness_filters:
        query = query.where(*freshness_filters)
    return query


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


def _load_preview_payload(
    *,
    context: RequestContext,
    db: Session,
    commodity: str | None,
    location: str | None,
    source_name: str | None,
    region: str | None,
    company_id: uuid.UUID | None,
    location_id: uuid.UUID | None,
    captured_date: date | None,
    include_non_canonical: bool,
    sort: str,
    limit: int,
) -> list[dict[str, object]]:
    enforce_latest = captured_date is None
    filters = _build_filters(
        commodity=commodity,
        location=location,
        source_name=source_name,
        region=region,
        captured_date=captured_date,
        company_id=company_id,
        location_id=location_id,
    )
    query: Select = _base_query(context, enforce_latest=enforce_latest)
    query = query.where(*_user_visible_market_filters(include_non_canonical))
    if filters:
        query = query.where(*filters)
    query = _with_sorting(query, sort)

    rows = db.execute(query.limit(limit * 3)).all()
    location_ids = {price.location_id for price, _snapshot in rows if price.location_id is not None}
    company_ids = {price.company_id for price, _snapshot in rows if price.company_id is not None}
    location_company_map = _load_location_company_map(db, location_ids=location_ids)
    company_ids.update(location_company_map.values())
    company_name_map = _load_company_name_map(db, company_ids=company_ids)
    deduped_rows: list[tuple[NormalizedPrice, PriceSnapshot]] = []
    seen: set[str] = set()
    for price, snapshot in rows:
        if _is_expired_market_period(price):
            continue
        dedupe_key = _preview_row_dedupe_key(
            price,
            company_name_map=company_name_map,
            location_company_map=location_company_map,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped_rows.append((price, snapshot))
        if len(deduped_rows) >= limit:
            break

    candidate_counts: dict[str, int] = {}
    if deduped_rows:
        key_count_query = (
            select(NormalizedPrice.composite_key, func.count(NormalizedPrice.id))
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .where(Source.org_id == context.org_id)
            .where(*_user_visible_market_filters(True))
            .where(NormalizedPrice.composite_key.in_([price.composite_key for price, _snapshot in deduped_rows]))
            .group_by(NormalizedPrice.composite_key)
        )
        freshness_filters = _snapshot_freshness_filters(enforce_latest=enforce_latest)
        if freshness_filters:
            key_count_query = key_count_query.where(*freshness_filters)
        if filters:
            key_count_query = key_count_query.where(*filters)
        for composite_key, count in db.execute(key_count_query).all():
            candidate_counts[str(composite_key)] = int(count)

    return [
        _serialize_preview_row(
            price,
            snapshot,
            candidate_counts,
            company_name_map,
            location_company_map,
        )
        for price, snapshot in deduped_rows
    ]


@router.get("")
def list_normalized_prices(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    region: str | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    captured_date: date | None = Query(None),
    include_non_canonical: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    enforce_latest = captured_date is None
    query: Select = _base_query(context, enforce_latest=enforce_latest).where(*_user_visible_market_filters(include_non_canonical)).order_by(desc(PriceSnapshot.captured_at), NormalizedPrice.location)

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

    rows = db.execute(query.limit(limit * 3)).all()
    filtered_rows: list[tuple[NormalizedPrice, PriceSnapshot]] = []
    for price, snapshot in rows:
        if _is_expired_market_period(price):
            continue
        filtered_rows.append((price, snapshot))
        if len(filtered_rows) >= limit:
            break
    company_name_map = _load_company_name_map(
        db,
        company_ids={price.company_id for price, _snapshot in filtered_rows if price.company_id is not None},
    )

    return {
        "rows": [
            {
                "id": str(price.id),
                "snapshot_id": str(price.snapshot_id),
                "company_id": str(price.company_id) if price.company_id else None,
                "location_id": str(price.location_id) if price.location_id else None,
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": canonical_location_name(price.location) or "-",
                "company_name": _display_company_name_for_row(price, company_name_map=company_name_map),
                "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
                "source_name": canonical_source_name(price.source_name),
                "source_attribution": _source_attribution_name(price.source_name),
                "delivery_start": normalize_text(price.delivery_start),
                "delivery_end": normalize_text(price.delivery_end),
                "delivery_label": _canonical_month_label(normalize_text(price.delivery_label)),
                "futures_month": _canonical_month_label(normalize_text(price.futures_month)),
                "futures_price": _to_float(price.futures_price),
                "futures_change": _coalesce_zero(_to_float(getattr(price, "futures_change", None))),
                "basis": _to_basis_float(price.basis),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_mt": _to_float(price.cash_price_mt),
                "basis_change": _coalesce_zero(_to_basis_float(price.basis_change)),
                "basis_last_changed_at": price.basis_last_changed_at.isoformat() if price.basis_last_changed_at else None,
                "cash_price_bu_change": _coalesce_zero(_to_float(price.cash_price_bu_change)),
                "cash_price_mt_change": _coalesce_zero(_to_float(price.cash_price_mt_change)),
                "composite_key": price.composite_key,
                "is_canonical": price.is_canonical,
                "canonical_rank": price.canonical_rank,
                "canonical_reason": price.canonical_reason,
            }
            for price, snapshot in filtered_rows
        ]
    }


@router.get("/facets")
def facets(
    captured_date: date | None = Query(None),
    include_non_canonical: bool = Query(False),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    enforce_latest = captured_date is None
    freshness_filters = _snapshot_freshness_filters(enforce_latest=enforce_latest)
    filters = _build_filters(
        commodity=None,
        location=None,
        source_name=None,
        region=None,
        captured_date=captured_date,
    )
    commodity_query = (
        select(func.distinct(NormalizedPrice.commodity_name))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .where(*_user_visible_market_filters(include_non_canonical))
    )
    if freshness_filters:
        commodity_query = commodity_query.where(*freshness_filters)
    location_query = (
        select(func.distinct(NormalizedPrice.location))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .where(*_user_visible_market_filters(include_non_canonical))
    )
    if freshness_filters:
        location_query = location_query.where(*freshness_filters)
    source_query = (
        select(func.distinct(NormalizedPrice.source_name))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .where(*_user_visible_market_filters(include_non_canonical))
    )
    if freshness_filters:
        source_query = source_query.where(*freshness_filters)
    if filters:
        commodity_query = commodity_query.where(*filters)
        location_query = location_query.where(*filters)
        source_query = source_query.where(*filters)

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
            display_name = _display_company_name(label)
            display_key = canonical_key(display_name)
            if display_name and display_key and display_key not in company_map:
                company_map[display_key] = display_name

    company_rows_query = (
        select(Company.id, Company.name, func.count(func.distinct(NormalizedPrice.composite_key)).label("market_count"))
        .join(NormalizedPrice, NormalizedPrice.company_id == Company.id)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .where(*_user_visible_market_filters(include_non_canonical))
        .group_by(Company.id, Company.name)
        .order_by(Company.name.asc())
    )
    if freshness_filters:
        company_rows_query = company_rows_query.where(*freshness_filters)
    location_rows_query = (
        select(
            Location.id,
            Location.name,
            Location.region,
            func.count(func.distinct(NormalizedPrice.composite_key)).label("market_count"),
        )
        .join(NormalizedPrice, NormalizedPrice.location_id == Location.id)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .where(*_user_visible_market_filters(include_non_canonical))
        .group_by(Location.id, Location.name, Location.region)
        .order_by(Location.name.asc())
    )
    if freshness_filters:
        location_rows_query = location_rows_query.where(*freshness_filters)
    if filters:
        company_rows_query = company_rows_query.where(*filters)
        location_rows_query = location_rows_query.where(*filters)

    company_rows = db.execute(company_rows_query).all()
    location_rows = db.execute(location_rows_query).all()

    deduped_companies: dict[str, dict[str, object]] = {}
    for company_id, name, market_count in company_rows:
        display_name = _display_company_name(name)
        if display_name is None:
            continue
        key = canonical_key(display_name)
        if not key or not display_name:
            continue
        if key not in deduped_companies:
            deduped_companies[key] = {"id": str(company_id), "name": display_name, "market_count": int(market_count or 0)}

    deduped_locations: dict[str, dict[str, object]] = {}
    for location_id, name, region, market_count in location_rows:
        display_name = canonical_location_name(name) or (name or "").strip()
        key = canonical_key(display_name)
        if not key or not display_name:
            continue
        if key not in deduped_locations:
            deduped_locations[key] = {
                "id": str(location_id),
                "name": display_name,
                "region": normalize_text(region),
                "market_count": int(market_count or 0),
            }

    fallback_company_market_counts: dict[str, int] = {}
    for location_row in deduped_locations.values():
        location_name = str(location_row.get("name") or "")
        location_key = canonical_key(location_name)
        if not location_key:
            continue
        fallback_company_name = LOCATION_COMPANY_DISPLAY_OVERRIDES.get(location_key)
        if not fallback_company_name:
            continue
        fallback_key = canonical_key(fallback_company_name)
        if not fallback_key:
            continue
        fallback_company_market_counts[fallback_key] = int(
            fallback_company_market_counts.get(fallback_key, 0)
        ) + int(location_row.get("market_count") or 0)

    company_identity_map = _load_company_display_identity_map(db, org_id=context.org_id)
    for fallback_key, fallback_market_count in fallback_company_market_counts.items():
        existing = deduped_companies.get(fallback_key)
        if existing is not None:
            existing["market_count"] = max(int(existing.get("market_count") or 0), int(fallback_market_count or 0))
            continue
        identity = company_identity_map.get(fallback_key)
        if identity is None:
            continue
        company_id, display_name = identity
        deduped_companies[fallback_key] = {
            "id": company_id,
            "name": display_name,
            "market_count": int(fallback_market_count or 0),
        }

    minimum_market_count = max(1, int(settings.user_visible_facet_min_market_count))
    company_row_values = _prune_facet_rows(list(deduped_companies.values()), minimum_market_count=minimum_market_count)
    forced_company_names = {
        company_name
        for company_name in LOCATION_COMPANY_DISPLAY_OVERRIDES.values()
        if company_name
    }
    company_row_values = _append_forced_company_rows(
        company_row_values,
        all_company_rows_by_key=deduped_companies,
        forced_company_names=forced_company_names,
    )
    location_row_values = _prune_facet_rows(list(deduped_locations.values()), minimum_market_count=minimum_market_count)
    company_name_values = sorted({str(row["name"]) for row in company_row_values})
    location_name_values = sorted({str(row["name"]) for row in location_row_values})

    return {
        "commodities": sorted(commodity_map.values()),
        "locations": location_name_values,
        "source_names": sorted([*company_name_values, *region_map.values()]),
        "company_names": company_name_values,
        "region_names": sorted(region_map.values()),
        "company_rows": sorted(company_row_values, key=lambda row: str(row["name"])),
        "location_rows": sorted(location_row_values, key=lambda row: str(row["name"])),
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
    include_non_canonical: bool = Query(False),
    sort: str = Query(
        "captured_desc",
        pattern="^(captured_desc|basis_desc|basis_asc|cash_bu_desc|cash_bu_asc|basis_change_desc)$",
    ),
    limit: int = Query(80, ge=1, le=250),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    return {
        "rows": _load_preview_payload(
            context=context,
            db=db,
            commodity=commodity,
            location=location,
            source_name=source_name,
            region=region,
            company_id=company_id,
            location_id=location_id,
            captured_date=captured_date,
            include_non_canonical=include_non_canonical,
            sort=sort,
            limit=limit,
        )
    }


@router.get("/preview-grouped")
def preview_grouped(
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    region: str | None = Query(None),
    company_id: uuid.UUID | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    captured_date: date | None = Query(None),
    include_non_canonical: bool = Query(False),
    sort: str = Query(
        "captured_desc",
        pattern="^(captured_desc|basis_desc|basis_asc|cash_bu_desc|cash_bu_asc|basis_change_desc)$",
    ),
    limit: int = Query(80, ge=1, le=250),
    rows_per_group: int = Query(8, ge=1, le=20),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = _load_preview_payload(
        context=context,
        db=db,
        commodity=commodity,
        location=location,
        source_name=source_name,
        region=region,
        company_id=company_id,
        location_id=location_id,
        captured_date=captured_date,
        include_non_canonical=include_non_canonical,
        sort=sort,
        limit=limit,
    )
    return {
        "groups": _group_preview_rows_by_delivery(rows, rows_per_group=rows_per_group),
        "row_count": len(rows),
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
    include_non_canonical: bool = Query(False),
    limit: int = Query(10, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    enforce_latest = captured_date is None
    query: Select = (
        select(NormalizedPrice, PriceSnapshot)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == context.org_id)
        .where(NormalizedPrice.basis_change.is_not(None))
        .where(*_user_visible_market_filters(include_non_canonical))
        .order_by(desc(func.abs(NormalizedPrice.basis_change)), desc(PriceSnapshot.captured_at))
    )
    freshness_filters = _snapshot_freshness_filters(enforce_latest=enforce_latest)
    if freshness_filters:
        query = query.where(*freshness_filters)

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

    rows = db.execute(query.limit(limit * 3)).all()
    filtered_rows: list[tuple[NormalizedPrice, PriceSnapshot]] = []
    for price, snapshot in rows:
        if _is_expired_market_period(price):
            continue
        filtered_rows.append((price, snapshot))
        if len(filtered_rows) >= limit:
            break
    company_name_map = _load_company_name_map(
        db,
        company_ids={price.company_id for price, _snapshot in filtered_rows if price.company_id is not None},
    )

    return {
        "rows": [
            {
                "id": str(price.id),
                "snapshot_id": str(price.snapshot_id),
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "location": canonical_location_name(price.location) or "-",
                "company_name": _display_company_name_for_row(price, company_name_map=company_name_map),
                "commodity_name": canonical_commodity_name(price.commodity_name) or "-",
                "source_name": canonical_source_name(price.source_name),
                "source_attribution": _source_attribution_name(price.source_name),
                "basis": _to_basis_float(price.basis),
                "basis_change": _coalesce_zero(_to_basis_float(price.basis_change)),
                "basis_last_changed_at": price.basis_last_changed_at.isoformat() if price.basis_last_changed_at else None,
                "futures_change": _coalesce_zero(_to_float(getattr(price, "futures_change", None))),
                "cash_price_bu": _to_float(price.cash_price_bu),
                "cash_price_bu_change": _coalesce_zero(_to_float(price.cash_price_bu_change)),
                "cash_price_mt": _to_float(price.cash_price_mt),
                "cash_price_mt_change": _coalesce_zero(_to_float(price.cash_price_mt_change)),
            }
            for price, snapshot in filtered_rows
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
    include_non_canonical: bool = Query(False),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    enforce_latest = captured_date is None
    freshness_filters = _snapshot_freshness_filters(enforce_latest=enforce_latest)
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
        .where(*_user_visible_market_filters(include_non_canonical))
    )
    if freshness_filters:
        basis_query = basis_query.where(*freshness_filters)
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
