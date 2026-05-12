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

from app.models.commodity import Commodity
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.raw_upload import RawUpload
from app.models.source import Source
from app.modules.imports.legacy_helpers import symbol_to_month_extended
from app.services.market_canonicalization import (
    canonical_commodity_name,
    canonical_location_name,
    canonical_source_name,
    normalize_text,
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

COLUMN_ALIASES = {
    "location": ["location", "site", "location_name", "elevator"],
    "commodity": ["commodity", "crop", "grain", "name"],
    "source_name": ["source_name", "source", "buyer", "company", "source_sheet", "sheet"],
    "delivery_start": ["delivery_start", "start", "start_date", "delivery start"],
    "delivery_end": ["delivery_end", "end", "end_date", "delivery end"],
    "delivery_label": ["delivery_label", "delivery", "delivery_end", "delivery period"],
    "futures_month": ["futures_month", "month", "futures contract", "symbol", "futures symbol", "futures mon."],
    "futures_price": ["futures_price", "futures", "fut_price"],
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
    # Handles values like "ZCN26 @ 6.34" where the price is bundled with the symbol.
    matches = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not matches:
        return None
    for token in reversed(matches):
        parsed = _parse_decimal(token)
        if parsed is not None:
            return parsed
    return None


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

        source_name = canonical_source_name(str(row.get(mapping.get("source_name", ""), "") or "").strip()) or canonical_source_name(source.name) or source.name
        delivery_start = normalize_text(str(row.get(mapping.get("delivery_start", ""), "") or "").strip()) or ""
        delivery_end = normalize_text(str(row.get(mapping.get("delivery_end", ""), "") or "").strip()) or ""
        delivery_label = normalize_text(str(row.get(mapping.get("delivery_label", ""), "") or "").strip()) or ""
        futures_month_raw = str(row.get(mapping.get("futures_month", ""), "") or "").strip()
        futures_month = normalize_text(symbol_to_month_extended(futures_month_raw) or futures_month_raw) or ""

        futures_price = _parse_decimal(str(row.get(mapping.get("futures_price", ""), "") or ""))
        basis = _parse_decimal(str(row.get(mapping.get("basis", ""), "") or ""))
        cash_price_bu = _parse_decimal(str(row.get(mapping.get("cash_price_bu", ""), "") or ""))
        cash_price_mt = _parse_decimal(str(row.get(mapping.get("cash_price_mt", ""), "") or ""))
        if cash_price_mt is None:
            cash_price_mt = _infer_cash_price_mt(commodity_name=commodity_name, cash_price_bu=cash_price_bu)
        if _is_blank(futures_month):
            futures_month = normalize_text(delivery_label or delivery_end or "") or ""
        if futures_price is None:
            futures_price = _extract_price_from_text(futures_month_raw)
        if futures_price is None and cash_price_bu is not None and basis is not None:
            futures_price = cash_price_bu - basis

        reject_reasons = _check_completeness(
            source_name=source_name,
            delivery_end=delivery_end,
            delivery_label=delivery_label,
            futures_month=futures_month,
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

        # If a source file repeats the same market key, keep the last row from that file.
        if composite_key in normalized_by_key:
            duplicate_key_count += 1
        normalized_by_key[composite_key] = NormalizedPrice(
            snapshot_id=snapshot.id,
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

    apply_historical_changes(db, normalized_rows=normalized_rows, captured_at=captured)
    db.add_all(normalized_rows)
    db.flush()
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
