from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commodity import Commodity
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.raw_upload import RawUpload
from app.models.source import Source


REQUIRED_CANONICAL_COLUMNS = {"location", "commodity"}
CANONICAL_COLUMNS = {
    "location",
    "commodity",
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


def _composite_key(location: str, commodity_name: str, delivery_label: str, futures_month: str) -> str:
    parts = [location.strip().lower(), commodity_name.strip().lower(), delivery_label.strip().lower(), futures_month.strip().lower()]
    return "|".join(parts)


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

    mapping = infer_column_mapping(headers, override=column_mapping_override)
    captured = captured_at or datetime.now(timezone.utc)

    snapshot = PriceSnapshot(
        source_id=source_id,
        commodity_id=commodity_id,
        captured_at=captured,
        raw_payload_json={"file_name": file_name, "headers": headers},
    )
    db.add(snapshot)
    db.flush()

    normalized_rows: list[NormalizedPrice] = []
    row_count = 0

    for row in reader:
        row_count += 1
        location = str(row.get(mapping["location"], "")).strip()
        commodity_name = str(row.get(mapping["commodity"], "")).strip() or commodity.name
        if not location or not commodity_name:
            continue

        delivery_label = str(row.get(mapping.get("delivery_label", ""), "")).strip()
        futures_month = str(row.get(mapping.get("futures_month", ""), "")).strip()

        futures_price = _parse_decimal(row.get(mapping.get("futures_price", "")))
        basis = _parse_decimal(row.get(mapping.get("basis", "")))
        cash_price_bu = _parse_decimal(row.get(mapping.get("cash_price_bu", "")))
        cash_price_mt = _parse_decimal(row.get(mapping.get("cash_price_mt", "")))

        normalized_rows.append(
            NormalizedPrice(
                snapshot_id=snapshot.id,
                location=location,
                commodity_name=commodity_name,
                delivery_label=delivery_label or None,
                futures_month=futures_month or None,
                futures_price=futures_price,
                basis=basis,
                cash_price_bu=cash_price_bu,
                cash_price_mt=cash_price_mt,
                basis_change=None,
                composite_key=_composite_key(location, commodity_name, delivery_label, futures_month),
            )
        )

    if not normalized_rows:
        raise ValueError("No valid data rows found after normalization")

    db.add_all(normalized_rows)

    upload = RawUpload(
        source_id=source_id,
        snapshot_id=snapshot.id,
        file_name=file_name,
        content_type=content_type,
        file_size_bytes=len(payload),
        row_count=row_count,
        raw_headers=headers,
        column_mapping=mapping,
        status="processed",
    )
    db.add(upload)
    db.commit()

    return CsvUploadResult(
        upload_id=upload.id,
        snapshot_id=snapshot.id,
        inserted_rows=len(normalized_rows),
        headers=headers,
        mapping=mapping,
    )
