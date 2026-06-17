from __future__ import annotations

from collections.abc import Iterable, Mapping
import uuid

from sqlalchemy import Select, or_

from app.models.normalized_price import NormalizedPrice
from app.services.market_canonicalization import canonical_key


def apply_market_search_filters(
    query: Select,
    *,
    filters: Mapping[str, object] | None,
    delivery_months: Iterable[str] | None = None,
) -> Select:
    normalized = _normalize_filters(filters)
    commodity_name = normalized.get("commodity_name")
    location = normalized.get("location")
    source_name = normalized.get("source_name")
    region = normalized.get("region")
    location_id = normalized.get("location_id")
    company_id = normalized.get("company_id")

    if commodity_name:
        query = query.where(NormalizedPrice.commodity_name.ilike(f"%{commodity_name}%"))
    if location:
        query = query.where(NormalizedPrice.location.ilike(f"%{location}%"))
    if source_name:
        query = query.where(NormalizedPrice.source_name.ilike(f"%{source_name}%"))
    if region:
        query = query.where(NormalizedPrice.source_name.ilike(f"%{region}%"))
    if location_id:
        parsed_location_id = _parse_uuid(location_id)
        if parsed_location_id is not None:
            query = query.where(NormalizedPrice.location_id == parsed_location_id)
    if company_id:
        parsed_company_id = _parse_uuid(company_id)
        if parsed_company_id is not None:
            query = query.where(NormalizedPrice.company_id == parsed_company_id)

    month_scope = _normalize_tokens(delivery_months)
    if month_scope:
        like_clauses = []
        for token in month_scope:
            like_clauses.append(NormalizedPrice.delivery_label.ilike(f"%{token}%"))
            like_clauses.append(NormalizedPrice.futures_month.ilike(f"%{token}%"))
        if like_clauses:
            query = query.where(or_(*like_clauses))

    return query


def row_matches_market_search_filters(
    row: NormalizedPrice,
    *,
    filters: Mapping[str, object] | None,
    delivery_months: Iterable[str] | None = None,
) -> bool:
    normalized = _normalize_filters(filters)
    commodity_name = normalized.get("commodity_name")
    location = normalized.get("location")
    source_name = normalized.get("source_name")
    region = normalized.get("region")
    location_id = normalized.get("location_id")
    company_id = normalized.get("company_id")

    if commodity_name and not _contains_casefold(row.commodity_name, commodity_name):
        return False
    if location and not _contains_casefold(row.location, location):
        return False
    if source_name and not _contains_casefold(row.source_name, source_name):
        return False
    if region and not _contains_casefold(row.source_name, region):
        return False
    if location_id and (row.location_id is None or str(row.location_id) != location_id):
        return False
    if company_id and (row.company_id is None or str(row.company_id) != company_id):
        return False

    month_scope = _normalize_tokens(delivery_months)
    if month_scope:
        row_tokens = " ".join(
            [
                (row.delivery_label or "").lower(),
                (row.delivery_end or "").lower(),
                (row.delivery_start or "").lower(),
                (row.futures_month or "").lower(),
            ]
        )
        if not row_tokens.strip():
            return False
        if not any(token in row_tokens for token in month_scope):
            return False

    return True


def _normalize_filters(filters: Mapping[str, object] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not filters:
        return normalized
    for key in ("commodity_name", "location", "source_name", "region", "location_id", "company_id"):
        value = filters.get(key)
        if value is None:
            continue
        stripped = str(value).strip()
        if stripped:
            normalized[key] = stripped
    return normalized


def _normalize_tokens(values: Iterable[str] | None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        if value is None:
            continue
        token = str(value).strip().lower()
        if not token:
            continue
        key = canonical_key(token) or token
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
    return tokens


def _contains_casefold(value: str | None, needle: str) -> bool:
    if not value:
        return False
    return needle.strip().lower() in value.strip().lower()


def _parse_uuid(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None
