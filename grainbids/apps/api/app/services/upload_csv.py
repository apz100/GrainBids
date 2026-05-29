from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.commodity import Commodity
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.raw_upload import RawUpload
from app.models.source import Source
from app.modules.imports.legacy_helpers import symbol_to_month_extended
from app.services.canonical_resolver import resolve_canonical_rows_for_snapshot
from app.services.market_canonicalization import (
    canonical_key,
    canonical_commodity_name,
    canonical_location_name,
    canonical_source_name,
    normalize_text,
    source_scope,
)
from app.services.price_comparison import apply_historical_changes, build_composite_key


REQUIRED_CANONICAL_COLUMNS = {"location", "commodity"}
REQUIRED_NORMALIZED_FIELDS = (
    "location",
    "commodity_name",
    "source_name",
    "delivery_window",
    "futures_month",
    "basis",
    "cash_price_bu",
    "cash_price_mt",
    "composite_key",
)
CANONICAL_COLUMNS = {
    "location",
    "commodity",
    "source_name",
    "delivery_start",
    "delivery_end",
    "delivery_label",
    "futures_month",
    "futures_price",
    "basis",
    "cash_price_bu",
    "cash_price_mt",
}

BUSHELS_PER_METRIC_TONNE = {
    "corn": Decimal("39.368"),
    "soybean": Decimal("36.744"),
    "soybeans": Decimal("36.744"),
    "wheat": Decimal("36.744"),
    "canola": Decimal("44.092"),
}

MONTH_TOKEN_TO_NUMBER = {
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

MONTH_NUMBER_TO_NAME = {
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

MONTH_NAME_PATTERN = re.compile(
    r"^(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    flags=re.IGNORECASE,
)

COLUMN_ALIASES = {
    "location": ["location", "site", "location_name", "elevator"],
    "commodity": ["commodity", "crop", "grain", "name"],
    "source_name": ["source_name", "source", "buyer", "company", "source_sheet", "sheet"],
    "delivery_start": ["delivery_start", "start", "start_date", "delivery start"],
    "delivery_end": ["delivery_end", "end", "end_date", "delivery end"],
    "delivery_label": ["delivery_label", "delivery", "delivery_end", "delivery period"],
    "futures_month": ["futures_month", "month", "futures contract", "symbol", "futures symbol", "futures mon."],
    "futures_price": ["futures_price", "futures", "fut_price"],
    "futures_change": ["futures_change", "fut_change", "change", "chg"],
    "basis": ["basis", "basis_value"],
    "cash_price_bu": ["cash_price_bu", "cash_bu", "cash price bu", "bushel cash price", "cash price", "the andersons cash price"],
    "cash_price_mt": [
        "cash_price_mt",
        "cash_mt",
        "cash price mt",
        "tonne cash price",
        "mt cash price",
        "cash price (tonne)",
        "convtd. price (tonnes)",
        "price / (tonnes)",
        "converted price",
    ],
}


@dataclass
class CsvUploadResult:
    upload_id: uuid.UUID
    snapshot_id: uuid.UUID
    inserted_rows: int
    headers: list[str]
    mapping: dict[str, str]
    parse_success_rate: float
    duplicate_key_count: int
    rejected_row_count: int
    missing_required_count: int
    row_reject_reasons: dict[str, int]


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    # Some feeds append trailing side markers (e.g. 455'6s).
    text = re.sub(r"(?<=\d)[A-Za-z]+$", "", text)
    if not text:
        return None
    tick_match = re.fullmatch(r"(-?\d+)\s*['-]\s*(\d+)", text)
    if tick_match:
        whole = Decimal(tick_match.group(1))
        frac = tick_match.group(2)
        # Common grain sheets use 1-digit eighths (e.g. 456'6 -> 456.75).
        if len(frac) == 1 and frac.isdigit():
            frac_value = Decimal(frac)
            if Decimal(0) <= frac_value <= Decimal(7):
                return whole + (frac_value / Decimal(8))
        text = f"{tick_match.group(1)}.{frac}"

    cleaned = text.replace(",", "").replace("$", "")
    if cleaned.strip().lower() in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
        return None
    try:
        parsed = Decimal(cleaned)
        if not parsed.is_finite():
            return None
        return parsed
    except InvalidOperation:
        return None


def _extract_price_from_text(value: str | None) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = text.replace(",", "")

    # First handle grain tick quotes like 455'6s.
    tick_matches = re.findall(r"-?\d+\s*['-]\s*\d+[A-Za-z]*", cleaned)
    for token in reversed(tick_matches):
        parsed = _parse_decimal(token)
        if parsed is not None:
            return parsed

    # Then handle explicit decimal prices (e.g. "ZCN26 @ 6.34").
    decimal_matches = re.findall(r"-?\d+\.\d+", cleaned)
    for token in reversed(decimal_matches):
        parsed = _parse_decimal(token)
        if parsed is not None:
            return parsed

    # Only accept integer fallback when the full token is numeric and in a realistic futures range.
    standalone_number = re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned)
    if standalone_number is not None:
        parsed = _parse_decimal(standalone_number.group(0))
        if parsed is not None and abs(parsed) <= Decimal("1200"):
            return parsed

    # Finally, accept numbers explicitly marked as prices (e.g. "$500", "@ 500").
    marked_matches = re.findall(r"(?:@|\$)\s*(-?\d+(?:\.\d+)?)", cleaned)
    for token in reversed(marked_matches):
        parsed = _parse_decimal(token)
        if parsed is not None:
            return parsed
    return None


def _looks_like_month_delivery_label(value: str | None) -> bool:
    normalized = normalize_text(value)
    if normalized is None:
        return False
    compact = re.sub(r"\s+", " ", normalized.replace(",", " ")).strip()
    if _derive_delivery_month_from_futures_month(compact) is not None:
        return True
    return MONTH_NAME_PATTERN.match(compact) is not None


def _derive_delivery_month_from_futures_month(futures_month: str | None) -> str | None:
    value = normalize_text(futures_month)
    if value is None:
        return None
    compact = re.sub(r"\s+", " ", value.replace(",", " ")).strip()
    match = re.match(r"^([A-Za-z]+)\s*([0-9]{2,4})$", compact)
    if match is None:
        return None

    month_token = match.group(1).casefold()
    year_token = match.group(2)
    month_number = MONTH_TOKEN_TO_NUMBER.get(month_token)
    if month_number is None:
        return None

    year_value = int(year_token)
    if len(year_token) == 2:
        year_value = 2000 + year_value
    if year_value < 1900 or year_value > 2200:
        return None

    if month_number == 1:
        return f"December {year_value - 1}"
    previous_month = month_number - 1
    return f"{MONTH_NUMBER_TO_NAME[previous_month]} {year_value}"


def _normalize_basis_value(basis: Decimal | None) -> Decimal | None:
    if basis is None:
        return None
    # Some source sheets emit basis in cents (e.g. 140) instead of dollars/bu (1.40).
    # GrainBids standard is dollars per bushel.
    if abs(basis) >= Decimal("10"):
        return (basis / Decimal("100")).quantize(Decimal("0.01"))
    return basis


def _infer_cash_price_mt(*, commodity_name: str, cash_price_bu: Decimal | None) -> Decimal | None:
    if cash_price_bu is None:
        return None
    key = commodity_name.strip().lower()
    factor = BUSHELS_PER_METRIC_TONNE.get(key)
    if factor is None:
        factor = BUSHELS_PER_METRIC_TONNE.get(key.rstrip("s"), BUSHELS_PER_METRIC_TONNE["corn"])
    return (cash_price_bu * factor).quantize(Decimal("0.01"))


def _is_invalid_commodity_name(commodity_name: str | None, source_name: str | None) -> bool:
    name = normalize_text(commodity_name)
    if name is None:
        return False
    key = name.casefold()
    if key in {"mixed daily file", "ontario daily file", "ontario cash bids", "eastern ontario daily file", "eastern ontario cash bids"}:
        return True
    if any(token in key for token in ("daily file", "cash bids", "source sheet")):
        return True
    source_key = canonical_key(source_name)
    return source_key is not None and key == source_key


def _decode_payload(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


def _normalize_header(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def infer_column_mapping(headers: list[str], override: dict[str, str] | None = None) -> dict[str, str]:
    normalized_lookup = {_normalize_header(header): header for header in headers}
    mapping: dict[str, str] = {}

    if override:
        for canonical, raw_column in override.items():
            if canonical in CANONICAL_COLUMNS and raw_column in headers:
                mapping[canonical] = raw_column

    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in mapping:
            continue
        for alias in aliases:
            if alias in headers:
                mapping[canonical] = alias
                break
            normalized = _normalize_header(alias)
            if normalized in normalized_lookup:
                mapping[canonical] = normalized_lookup[normalized]
                break

    missing_required = REQUIRED_CANONICAL_COLUMNS - set(mapping.keys())
    if missing_required:
        required = ", ".join(sorted(missing_required))
        raise ValueError(f"missing required mapped columns: {required}")

    return mapping


@dataclass
class NormalizedPersistResult:
    snapshot_id: uuid.UUID
    inserted_rows: int
    raw_row_count: int
    headers: list[str]
    mapping: dict[str, str]
    parse_success_rate: float
    duplicate_key_count: int
    rejected_row_count: int
    missing_required_count: int
    row_reject_reasons: dict[str, int]
    row_reject_breakdown: dict[str, dict]


def persist_normalized_rows(
    db: Session,
    *,
    source: Source,
    commodity: Commodity,
    rows: list[Mapping[str, object]],
    headers: list[str],
    captured_at: datetime | None = None,
    column_mapping_override: dict[str, str] | None = None,
    raw_payload_json: dict | None = None,
    fail_on_empty: bool = True,
) -> NormalizedPersistResult:
    if not headers:
        raise ValueError("source file has no header row")

    mapping = infer_column_mapping(headers, override=column_mapping_override)
    captured = captured_at or datetime.now(timezone.utc)

    snapshot = PriceSnapshot(
        source_id=source.id,
        commodity_id=commodity.id,
        captured_at=captured,
        raw_payload_json=raw_payload_json or {"headers": headers},
    )
    db.add(snapshot)
    db.flush()

    normalized_by_key: dict[str, NormalizedPrice] = {}
    company_cache: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
    location_cache: dict[tuple[uuid.UUID, str], tuple[uuid.UUID, uuid.UUID | None]] = {}
    company_name_cache: dict[uuid.UUID, str | None] = {}
    row_count = 0
    duplicate_key_count = 0
    rejected_row_count = 0
    missing_required_count = 0
    row_reject_reasons: dict[str, int] = {}
    row_reject_by_source: dict[str, dict[str, int]] = {}
    row_reject_by_field: dict[str, int] = {}

    for row in rows:
        row_count += 1
        location = canonical_location_name(str(row.get(mapping["location"], "") or "").strip()) or ""
        commodity_name = canonical_commodity_name(str(row.get(mapping["commodity"], "") or "").strip()) or canonical_commodity_name(commodity.name) or ""
        source_name = canonical_source_name(str(row.get(mapping.get("source_name", ""), "") or "").strip()) or canonical_source_name(source.name) or source.name
        if _is_blank(location):
            rejected_row_count += 1
            missing_required_count += 1
            _increment_reason(row_reject_reasons, "missing_location")
            continue
        if _is_blank(commodity_name):
            rejected_row_count += 1
            missing_required_count += 1
            _increment_reason(row_reject_reasons, "missing_commodity_name")
            continue
        if _is_invalid_commodity_name(commodity_name, source_name):
            rejected_row_count += 1
            missing_required_count += 1
            _increment_reason(row_reject_reasons, "invalid_commodity_name")
            continue

        delivery_start = normalize_text(str(row.get(mapping.get("delivery_start", ""), "") or "").strip()) or ""
        delivery_end = normalize_text(str(row.get(mapping.get("delivery_end", ""), "") or "").strip()) or ""
        delivery_label = normalize_text(str(row.get(mapping.get("delivery_label", ""), "") or "").strip()) or ""
        futures_month_raw = str(row.get(mapping.get("futures_month", ""), "") or "").strip()
        futures_month = normalize_text(symbol_to_month_extended(futures_month_raw) or futures_month_raw) or ""

        futures_price = _parse_decimal(str(row.get(mapping.get("futures_price", ""), "") or ""))
        futures_change = _parse_decimal(str(row.get(mapping.get("futures_change", ""), "") or ""))
        basis = _normalize_basis_value(_parse_decimal(str(row.get(mapping.get("basis", ""), "") or "")))
        cash_price_bu = _parse_decimal(str(row.get(mapping.get("cash_price_bu", ""), "") or ""))
        cash_price_mt = _parse_decimal(str(row.get(mapping.get("cash_price_mt", ""), "") or ""))
        if cash_price_mt is None:
            cash_price_mt = _infer_cash_price_mt(commodity_name=commodity_name, cash_price_bu=cash_price_bu)
        if _is_blank(futures_month):
            futures_month = normalize_text(delivery_label or delivery_end or "") or ""
        derived_delivery = _derive_delivery_month_from_futures_month(futures_month)
        has_month_delivery_label = _looks_like_month_delivery_label(delivery_label) or _looks_like_month_delivery_label(delivery_end)
        if derived_delivery and not has_month_delivery_label:
            delivery_end = derived_delivery
            delivery_label = derived_delivery
        if futures_price is None:
            futures_price = _extract_price_from_text(futures_month_raw)
        if futures_price is None and cash_price_bu is not None and basis is not None:
            futures_price = cash_price_bu - basis

        reject_reasons = _check_completeness(
            source_name=source_name,
            delivery_end=delivery_end,
            delivery_label=delivery_label,
            futures_month=futures_month,
            futures_month_raw=futures_month_raw,
            futures_change=futures_change,
            basis=basis,
            cash_price_bu=cash_price_bu,
            cash_price_mt=cash_price_mt,
        )
        if reject_reasons:
            rejected_row_count += 1
            source_key = source_name.strip() or "unknown_source"
            for reason in reject_reasons:
                _increment_reason(row_reject_reasons, reason)
                _increment_nested_reason(row_reject_by_source, source_key, reason)
                _increment_reason(row_reject_by_field, _field_name_from_reason(reason))
                if reason.startswith("missing_"):
                    missing_required_count += 1
            continue

        composite_key = build_composite_key(
            location=location,
            commodity_name=commodity_name,
            delivery_start=delivery_start,
            delivery_end=delivery_end,
            futures_month=futures_month,
        )
        if _is_blank(composite_key):
            rejected_row_count += 1
            missing_required_count += 1
            _increment_reason(row_reject_reasons, "missing_composite_key")
            continue

        company_id = _resolve_company_id_for_row(
            db,
            org_id=source.org_id,
            source_name=source_name,
            company_cache=company_cache,
        )
        location_id, location_company_id = _resolve_location_id(
            db,
            org_id=source.org_id,
            company_id=company_id,
            location_name=location,
            region=source.region,
            cache=location_cache,
            company_name_cache=company_name_cache,
        )
        company_id = _choose_company_id_for_row(
            source_name=source_name,
            explicit_company_id=company_id,
            location_company_id=location_company_id,
        )

        # If a source file repeats the same market key, keep the last row from that file.
        if composite_key in normalized_by_key:
            duplicate_key_count += 1
        normalized_by_key[composite_key] = NormalizedPrice(
            snapshot_id=snapshot.id,
            company_id=company_id,
            location_id=location_id,
            location=location,
            commodity_name=commodity_name,
            source_name=source_name,
            delivery_start=delivery_start or None,
            delivery_end=delivery_end or None,
            delivery_label=delivery_label or None,
            futures_month=futures_month or None,
            futures_price=futures_price,
            basis=basis,
            cash_price_bu=cash_price_bu,
            cash_price_mt=cash_price_mt,
            basis_change=None,
            basis_change_strict=None,
            basis_last_changed_at=None,
            cash_price_bu_change=None,
            cash_price_mt_change=None,
            composite_key=composite_key,
        )

    normalized_rows = list(normalized_by_key.values())
    if not normalized_rows:
        if fail_on_empty:
            detail = ", ".join(f"{key}:{value}" for key, value in sorted(row_reject_reasons.items()))
            raise ValueError(f"No valid data rows found after normalization ({detail or 'all rows rejected'})")
        parse_success_rate = float((row_count - rejected_row_count) / row_count) if row_count else 0.0
        return NormalizedPersistResult(
            snapshot_id=snapshot.id,
            inserted_rows=0,
            raw_row_count=row_count,
            headers=headers,
            mapping=mapping,
            parse_success_rate=parse_success_rate,
            duplicate_key_count=duplicate_key_count,
            rejected_row_count=rejected_row_count,
            missing_required_count=missing_required_count,
            row_reject_reasons=row_reject_reasons,
            row_reject_breakdown={
                "by_source": row_reject_by_source,
                "by_field": row_reject_by_field,
            },
        )

    apply_historical_changes(
        db,
        normalized_rows=normalized_rows,
        captured_at=captured,
        org_id=source.org_id,
    )
    db.add_all(normalized_rows)
    db.flush()
    resolve_canonical_rows_for_snapshot(
        db,
        org_id=source.org_id,
        snapshot_id=snapshot.id,
    )
    parse_success_rate = float((row_count - rejected_row_count) / row_count) if row_count else 0.0

    return NormalizedPersistResult(
        snapshot_id=snapshot.id,
        inserted_rows=len(normalized_rows),
        raw_row_count=row_count,
        headers=headers,
        mapping=mapping,
        parse_success_rate=parse_success_rate,
        duplicate_key_count=duplicate_key_count,
        rejected_row_count=rejected_row_count,
        missing_required_count=missing_required_count,
        row_reject_reasons=row_reject_reasons,
        row_reject_breakdown={
            "by_source": row_reject_by_source,
            "by_field": row_reject_by_field,
        },
    )


def process_csv_upload(
    db: Session,
    *,
    source_id: uuid.UUID,
    commodity_id: uuid.UUID,
    file_name: str,
    content_type: str | None,
    payload: bytes,
    captured_at: datetime | None = None,
    column_mapping_override: dict[str, str] | None = None,
) -> CsvUploadResult:
    source = db.execute(select(Source).where(Source.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ValueError("source_id not found")

    commodity = db.execute(select(Commodity).where(Commodity.id == commodity_id)).scalar_one_or_none()
    if commodity is None:
        raise ValueError("commodity_id not found")

    decoded = _decode_payload(payload)
    reader = csv.DictReader(io.StringIO(decoded))
    headers = list(reader.fieldnames or [])
    if not headers:
        raise ValueError("CSV file has no header row")

    source_rows = list(reader)
    persisted = persist_normalized_rows(
        db,
        source=source,
        commodity=commodity,
        rows=source_rows,
        headers=headers,
        captured_at=captured_at,
        column_mapping_override=column_mapping_override,
        raw_payload_json={"file_name": file_name, "headers": headers},
    )

    upload = RawUpload(
        source_id=source_id,
        snapshot_id=persisted.snapshot_id,
        file_name=file_name,
        content_type=content_type,
        file_size_bytes=len(payload),
        row_count=persisted.raw_row_count,
        raw_headers=headers,
        column_mapping=persisted.mapping,
        status="processed",
    )
    db.add(upload)
    db.commit()

    return CsvUploadResult(
        upload_id=upload.id,
        snapshot_id=persisted.snapshot_id,
        inserted_rows=persisted.inserted_rows,
        headers=headers,
        mapping=persisted.mapping,
        parse_success_rate=persisted.parse_success_rate,
        duplicate_key_count=persisted.duplicate_key_count,
        rejected_row_count=persisted.rejected_row_count,
        missing_required_count=persisted.missing_required_count,
        row_reject_reasons=persisted.row_reject_reasons,
    )


def _check_completeness(
    *,
    source_name: str | None,
    delivery_end: str | None,
    delivery_label: str | None,
    futures_month: str | None,
    futures_month_raw: str | None,
    futures_change: Decimal | None,
    basis: Decimal | None,
    cash_price_bu: Decimal | None,
    cash_price_mt: Decimal | None,
) -> list[str]:
    reasons: list[str] = []
    if _is_blank(source_name):
        reasons.append("missing_source_name")
    if _is_blank(delivery_end) and _is_blank(delivery_label):
        reasons.append("missing_delivery_window")
    if _is_blank(futures_month):
        reasons.append("missing_futures_month")
    if basis is None:
        reasons.append("missing_basis")
    if cash_price_bu is None:
        reasons.append("missing_cash_price_bu")
    if cash_price_mt is None:
        reasons.append("missing_cash_price_mt")
    source_key = (canonical_source_name(source_name) or source_name or "").strip().casefold()
    if source_key in {"snobelen", "snobelen farms", "ganaraska", "ganaraska grain"} and futures_change is None:
        reasons.append("missing_futures_change")
    if source_key in {"snobelen", "snobelen farms"} and _is_blank(futures_month_raw):
        reasons.append("missing_futures_month_source")
    return reasons


def summarize_quality(
    *,
    raw_row_count: int | None,
    normalized_row_count: int | None,
    duplicate_key_count: int | None,
    rejected_row_count: int | None,
    missing_required_count: int | None,
    parse_success_rate: float | None,
    row_reject_reasons: dict[str, int] | None,
) -> dict[str, object]:
    raw = int(raw_row_count or 0)
    normalized = int(normalized_row_count or 0)
    rejected = int(rejected_row_count or 0)
    duplicates = int(duplicate_key_count or 0)
    missing = int(missing_required_count or 0)
    success_rate = float(parse_success_rate) if parse_success_rate is not None else (float(normalized / raw) if raw else 0.0)
    return {
        "required_normalized_fields": list(REQUIRED_NORMALIZED_FIELDS),
        "raw_row_count": raw,
        "normalized_row_count": normalized,
        "rejected_row_count": rejected,
        "duplicate_key_count": duplicates,
        "missing_required_count": missing,
        "parse_success_rate": success_rate,
        "rejection_rate": float(rejected / raw) if raw else 0.0,
        "row_reject_reasons": row_reject_reasons or {},
    }


def _increment_reason(counter: dict[str, int], reason: str) -> None:
    counter[reason] = int(counter.get(reason, 0)) + 1


def _increment_nested_reason(counter: dict[str, dict[str, int]], bucket: str, reason: str) -> None:
    section = counter.get(bucket)
    if section is None:
        section = {}
        counter[bucket] = section
    section[reason] = int(section.get(reason, 0)) + 1


def _field_name_from_reason(reason: str) -> str:
    if reason.startswith("missing_"):
        return reason[len("missing_") :]
    return reason


def _is_blank(value: str | None) -> bool:
    return not str(value or "").strip()


def _resolve_company_id(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_name: str,
    cache: dict[tuple[uuid.UUID, str], uuid.UUID],
) -> uuid.UUID | None:
    normalized = normalize_text(source_name)
    if not normalized:
        return None
    key = normalized.casefold()
    cache_key = (org_id, key)
    if cache_key in cache:
        return cache[cache_key]

    row = db.execute(
        select(Company).where(
            Company.org_id == org_id,
            Company.canonical_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        row = Company(org_id=org_id, name=normalized, canonical_key=key)
        db.add(row)
        db.flush()
    cache[cache_key] = row.id
    return row.id


def _source_creates_company_identity(source_name: str | None) -> bool:
    scope, label = source_scope(source_name)
    if scope != "company":
        return False
    key = canonical_key(label)
    if key is None:
        return False
    return key not in settings.canonical_aggregator_sources_set


def _resolve_company_id_for_row(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_name: str,
    company_cache: dict[tuple[uuid.UUID, str], uuid.UUID],
) -> uuid.UUID | None:
    if not _source_creates_company_identity(source_name):
        return None
    return _resolve_company_id(
        db,
        org_id=org_id,
        source_name=source_name,
        cache=company_cache,
    )


def _choose_company_id_for_row(
    *,
    source_name: str | None,
    explicit_company_id: uuid.UUID | None,
    location_company_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if explicit_company_id is not None:
        return explicit_company_id
    if _source_creates_company_identity(source_name):
        return None
    return location_company_id


def _resolve_location_id(
    db: Session,
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID | None,
    location_name: str,
    region: str | None,
    cache: dict[tuple[uuid.UUID, str], tuple[uuid.UUID, uuid.UUID | None]],
    company_name_cache: dict[uuid.UUID, str | None],
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    normalized = canonical_location_name(location_name)
    if not normalized:
        return None, None
    key = normalized.casefold()
    cache_key = (org_id, key)
    if cache_key in cache:
        return cache[cache_key]

    row = db.execute(
        select(Location).where(
            Location.org_id == org_id,
            Location.canonical_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        trusted_company_id = company_id if company_id is not None else None
        row = Location(
            org_id=org_id,
            company_id=trusted_company_id,
            name=normalized,
            canonical_key=key,
            region=normalize_text(region),
        )
        db.add(row)
        db.flush()
    else:
        existing_company_id = _trusted_location_company_id(
            db,
            company_id=row.company_id,
            company_name_cache=company_name_cache,
        )
        if existing_company_id is None and company_id is not None:
            row.company_id = company_id
            existing_company_id = company_id
        if row.region is None and normalize_text(region):
            row.region = normalize_text(region)
        elif row.company_id != existing_company_id:
            row.company_id = existing_company_id
    trusted_company_id = _trusted_location_company_id(
        db,
        company_id=row.company_id,
        company_name_cache=company_name_cache,
    )
    cache[cache_key] = (row.id, trusted_company_id)
    return row.id, trusted_company_id


def _trusted_location_company_id(
    db: Session,
    *,
    company_id: uuid.UUID | None,
    company_name_cache: dict[uuid.UUID, str | None],
) -> uuid.UUID | None:
    if company_id is None:
        return None
    company_name = company_name_cache.get(company_id)
    if company_name is None and company_id not in company_name_cache:
        company_name = db.execute(select(Company.name).where(Company.id == company_id)).scalar_one_or_none()
        company_name_cache[company_id] = company_name
    if not _source_creates_company_identity(company_name):
        return None
    return company_id
