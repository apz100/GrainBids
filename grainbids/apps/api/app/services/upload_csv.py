from __future__ import annotations

import csv
import io
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
from app.services.price_comparison import apply_historical_changes, build_composite_key


REQUIRED_CANONICAL_COLUMNS = {"location", "commodity"}
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

COLUMN_ALIASES = {
    "location": ["location", "site", "location_name", "elevator"],
    "commodity": ["commodity", "crop", "grain", "name"],
    "source_name": ["source_name", "source", "buyer", "company"],
    "delivery_start": ["delivery_start", "start", "start_date", "delivery start"],
    "delivery_end": ["delivery_end", "end", "end_date", "delivery end"],
    "delivery_label": ["delivery_label", "delivery", "delivery_end", "delivery period"],
    "futures_month": ["futures_month", "month", "futures contract"],
    "futures_price": ["futures_price", "futures", "fut_price"],
    "basis": ["basis", "basis_value"],
    "cash_price_bu": ["cash_price_bu", "cash_bu", "cash price bu", "bushel cash price"],
    "cash_price_mt": ["cash_price_mt", "cash_mt", "cash price mt", "tonne cash price", "mt cash price"],
}


@dataclass
class CsvUploadResult:
    upload_id: uuid.UUID
    snapshot_id: uuid.UUID
    inserted_rows: int
    headers: list[str]
    mapping: dict[str, str]


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace(",", "").replace("$", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
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

    for row in rows:
        row_count += 1
        location = str(row.get(mapping["location"], "") or "").strip()
        commodity_name = str(row.get(mapping["commodity"], "") or "").strip() or commodity.name
        if not location or not commodity_name:
            continue

        source_name = str(row.get(mapping.get("source_name", ""), "") or "").strip() or source.name
        delivery_start = str(row.get(mapping.get("delivery_start", ""), "") or "").strip()
        delivery_end = str(row.get(mapping.get("delivery_end", ""), "") or "").strip()
        delivery_label = str(row.get(mapping.get("delivery_label", ""), "") or "").strip()
        futures_month = str(row.get(mapping.get("futures_month", ""), "") or "").strip()

        futures_price = _parse_decimal(str(row.get(mapping.get("futures_price", ""), "") or ""))
        basis = _parse_decimal(str(row.get(mapping.get("basis", ""), "") or ""))
        cash_price_bu = _parse_decimal(str(row.get(mapping.get("cash_price_bu", ""), "") or ""))
        cash_price_mt = _parse_decimal(str(row.get(mapping.get("cash_price_mt", ""), "") or ""))

        composite_key = build_composite_key(
            location=location,
            commodity_name=commodity_name,
            delivery_start=delivery_start,
            delivery_end=delivery_end,
            futures_month=futures_month,
        )

        # If a source file repeats the same market key, keep the last row from that file.
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
        raise ValueError("No valid data rows found after normalization")

    apply_historical_changes(db, normalized_rows=normalized_rows, captured_at=captured)
    db.add_all(normalized_rows)
    db.flush()

    return NormalizedPersistResult(
        snapshot_id=snapshot.id,
        inserted_rows=len(normalized_rows),
        raw_row_count=row_count,
        headers=headers,
        mapping=mapping,
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
    )
