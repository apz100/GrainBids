from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import time

import pandas as pd
import requests
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.commodity import Commodity
from app.models.ingestion_run import IngestionRun
from app.models.source import Source
from app.modules.imports.legacy_normalize import normalize_legacy_dataframe
from app.services.alert_evaluator import evaluate_alert_rules_for_snapshot
from app.services.source_health import record_source_health_snapshot, update_source_health_state
from app.services.upload_csv import infer_column_mapping, persist_normalized_rows


@dataclass
class SourceFileIngestionResult:
    run_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    source_identifier: str
    status: str
    trigger_type: str
    attempt_number: int
    max_attempts: int
    raw_row_count: int | None
    normalized_row_count: int | None
    created_alert_count: int
    deduped_alert_count: int
    duplicate_key_count: int
    rejected_row_count: int
    missing_required_count: int
    parse_success_rate: float | None
    row_reject_reasons: dict | None
    error_message: str | None


@dataclass
class FileSourceReprocessTarget:
    source_id: uuid.UUID
    source_name: str
    commodity_id: uuid.UUID
    snapshot_id: uuid.UUID
    captured_at: datetime | None
    source_file_path: str


COMMODITY_ALIASES: dict[str, str] = {
    "corn": "Corn",
    "maize": "Corn",
    "soybean": "Soybeans",
    "soybeans": "Soybeans",
    "soy": "Soybeans",
    "wheat": "Wheat",
}


def _read_source_file(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    if not path.exists():
        raise ValueError(f"source file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"source path is not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
        headers = [str(column) for column in df.columns.tolist()]
        rows = df.where(pd.notnull(df), None).to_dict(orient="records")
        return rows, headers
    elif suffix in {".xlsx", ".xls"}:
        return _read_multi_sheet_workbook(path)
    else:
        raise ValueError("source file must be .csv, .xlsx, or .xls")


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _read_source_url(url: str) -> tuple[list[dict[str, object]], list[str]]:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    payload = response.content
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix == ".csv":
        text = payload.decode("utf-8-sig", errors="replace")
        df = pd.read_csv(io.StringIO(text))
        headers = [str(column) for column in df.columns.tolist()]
        rows = df.where(pd.notnull(df), None).to_dict(orient="records")
        return rows, headers
    if suffix in {".xlsx", ".xls"}:
        workbook = pd.read_excel(io.BytesIO(payload), sheet_name=None)
        return _read_multi_sheet_workbook_from_dataframes(workbook, source_label=url)
    raise ValueError("source URL must end with .csv, .xlsx, or .xls")


def _read_multi_sheet_workbook_from_dataframes(
    workbook: dict[str, pd.DataFrame],
    *,
    source_label: str,
) -> tuple[list[dict[str, object]], list[str]]:
    canonical_headers = [
        "location",
        "commodity",
        "source_name",
        "delivery_start",
        "delivery_end",
        "delivery_label",
        "futures_month",
        "futures_price",
        "futures_change",
        "basis",
        "cash_price_bu",
        "cash_price_mt",
    ]
    merged_rows: list[dict[str, object]] = []
    for sheet_name, sheet_df in workbook.items():
        if sheet_df is None or sheet_df.empty:
            continue
        normalized = normalize_legacy_dataframe(sheet_df)
        if normalized.empty:
            continue
        for row in normalized.where(pd.notnull(normalized), None).to_dict(orient="records"):
            delivery_end = str(row.get("delivery_end", "") or "").strip()
            source_name = str(row.get("source_sheet", "") or "").strip() or str(sheet_name).strip()
            merged_rows.append(
                {
                    "location": row.get("location"),
                    "commodity": row.get("commodity"),
                    "source_name": source_name,
                    "delivery_start": "",
                    "delivery_end": delivery_end,
                    "delivery_label": delivery_end,
                    "futures_month": row.get("futures_month"),
                    "futures_price": row.get("futures_price"),
                    "futures_change": row.get("futures_change"),
                    "basis": row.get("basis"),
                    "cash_price_bu": row.get("cash_price_bu"),
                    "cash_price_mt": row.get("cash_price_mt"),
                }
            )

    if not merged_rows:
        raise ValueError(f"workbook has no readable rows: {source_label}")
    return merged_rows, canonical_headers

    
def _read_multi_sheet_workbook(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    workbook = pd.read_excel(path, sheet_name=None)
    return _read_multi_sheet_workbook_from_dataframes(workbook, source_label=str(path))


def _read_source_input(source_identifier: str) -> tuple[list[dict[str, object]], list[str]]:
    if _is_http_url(source_identifier):
        return _read_source_url(source_identifier)
    return _read_source_file(Path(source_identifier))


def _get_source(db: Session, source_id: uuid.UUID) -> Source:
    source = db.execute(select(Source).where(Source.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ValueError("source_id not found")
    return source


def _get_commodity(db: Session, commodity_id: uuid.UUID) -> Commodity:
    commodity = db.execute(select(Commodity).where(Commodity.id == commodity_id)).scalar_one_or_none()
    if commodity is None:
        raise ValueError("commodity_id not found")
    return commodity


def _commodity_key(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _display_commodity_name(raw_name: str) -> str:
    key = _commodity_key(raw_name)
    if key in COMMODITY_ALIASES:
        return COMMODITY_ALIASES[key]
    if not raw_name.strip():
        return ""
    return " ".join(part.capitalize() for part in raw_name.strip().split())


def _load_commodity_cache(db: Session) -> dict[str, Commodity]:
    cache: dict[str, Commodity] = {}
    for commodity in db.execute(select(Commodity).order_by(Commodity.name.asc())).scalars().all():
        cache[_commodity_key(commodity.name)] = commodity
    return cache


def _resolve_commodity_for_row(
    db: Session,
    *,
    cache: dict[str, Commodity],
    raw_name: str,
    fallback_commodity: Commodity | None,
) -> Commodity:
    display_name = _display_commodity_name(raw_name)
    if display_name:
        key = _commodity_key(display_name)
        existing = cache.get(key)
        if existing:
            return existing
        created = Commodity(name=display_name, unit="bu", conversion_factor=1)
        db.add(created)
        db.flush()
        cache[key] = created
        return created

    if fallback_commodity is not None:
        return fallback_commodity

    if cache:
        return next(iter(cache.values()))

    created = Commodity(name="Unknown", unit="bu", conversion_factor=1)
    db.add(created)
    db.flush()
    cache[_commodity_key(created.name)] = created
    return created


def _group_rows_by_commodity(
    db: Session,
    *,
    rows: list[dict[str, object]],
    headers: list[str],
    fallback_commodity: Commodity | None,
) -> list[tuple[Commodity, list[dict[str, object]]]]:
    mapping: dict[str, str] = {}
    try:
        mapping = infer_column_mapping(headers)
    except Exception:
        mapping = {}
    commodity_column = mapping.get("commodity")

    cache = _load_commodity_cache(db)
    grouped: dict[uuid.UUID, tuple[Commodity, list[dict[str, object]]]] = {}
    for row in rows:
        raw_commodity = str(row.get(commodity_column, "") or "").strip() if commodity_column else ""
        commodity = _resolve_commodity_for_row(
            db,
            cache=cache,
            raw_name=raw_commodity,
            fallback_commodity=fallback_commodity,
        )
        group = grouped.get(commodity.id)
        if group is None:
            grouped[commodity.id] = (commodity, [row])
        else:
            group[1].append(row)
    return list(grouped.values())


def ingest_source_file(
    db: Session,
    *,
    source_file_path: str,
    source_name: str,
    source_id: uuid.UUID,
    commodity_id: uuid.UUID | None,
    trigger_type: str = "manual",
    attempt_number: int = 1,
    max_attempts: int = 1,
    captured_at: datetime | None = None,
) -> SourceFileIngestionResult:
    source_identifier = str(Path(source_file_path))
    source = _get_source(db, source_id)
    run = IngestionRun(
        source_name=source.name,
        source_identifier=source_identifier,
        started_at=datetime.now(timezone.utc),
        status="running",
        trigger_type=trigger_type,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    created_alert_count = 0
    deduped_alert_count = 0
    duplicate_key_count = 0
    rejected_row_count = 0
    missing_required_count = 0
    parse_success_rate: float | None = None
    row_reject_reasons: dict | None = None
    schema_drift_count = 0
    latency_ms: int | None = None

    try:
        started = datetime.now(timezone.utc)
        rows, headers = _read_source_input(source_file_path)
        fallback_commodity = _get_commodity(db, commodity_id) if commodity_id else None
        row_groups = _group_rows_by_commodity(
            db,
            rows=rows,
            headers=headers,
            fallback_commodity=fallback_commodity,
        )

        total_raw_rows = 0
        total_inserted_rows = 0
        total_duplicate_key_count = 0
        total_rejected_row_count = 0
        total_missing_required_count = 0
        total_success_rows = 0.0
        merged_reject_reasons: dict[str, int] = {}
        merged_reject_by_source: dict[str, dict[str, int]] = {}
        merged_reject_by_field: dict[str, int] = {}
        snapshot_ids: list[uuid.UUID] = []

        for commodity, grouped_rows in row_groups:
            persisted = persist_normalized_rows(
                db,
                source=source,
                commodity=commodity,
                rows=grouped_rows,
                headers=headers,
                captured_at=captured_at,
                raw_payload_json={
                    "source_file_path": source_identifier,
                    "headers": headers,
                    "ingestion_run_id": str(run.id),
                    "commodity_id": str(commodity.id),
                    "commodity_name": commodity.name,
                },
                fail_on_empty=False,
            )
            snapshot_ids.append(persisted.snapshot_id)
            total_raw_rows += persisted.raw_row_count
            total_inserted_rows += persisted.inserted_rows
            total_duplicate_key_count += persisted.duplicate_key_count
            total_rejected_row_count += persisted.rejected_row_count
            total_missing_required_count += persisted.missing_required_count
            total_success_rows += persisted.parse_success_rate * persisted.raw_row_count
            for reason, count in (persisted.row_reject_reasons or {}).items():
                merged_reject_reasons[reason] = int(merged_reject_reasons.get(reason, 0)) + int(count)
            breakdown = persisted.row_reject_breakdown or {}
            by_source = breakdown.get("by_source", {}) if isinstance(breakdown, dict) else {}
            by_field = breakdown.get("by_field", {}) if isinstance(breakdown, dict) else {}
            if isinstance(by_source, dict):
                for source_label, reasons in by_source.items():
                    if not isinstance(reasons, dict):
                        continue
                    bucket = merged_reject_by_source.get(str(source_label))
                    if bucket is None:
                        bucket = {}
                        merged_reject_by_source[str(source_label)] = bucket
                    for reason, count in reasons.items():
                        bucket[str(reason)] = int(bucket.get(str(reason), 0)) + int(count)
            if isinstance(by_field, dict):
                for field_name, count in by_field.items():
                    merged_reject_by_field[str(field_name)] = int(merged_reject_by_field.get(str(field_name), 0)) + int(count)

        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        parse_success_rate = float(total_success_rows / total_raw_rows) if total_raw_rows else 0.0
        duplicate_key_count = total_duplicate_key_count
        rejected_row_count = total_rejected_row_count
        missing_required_count = total_missing_required_count
        row_reject_reasons = dict(merged_reject_reasons)
        row_reject_reasons["_by_source"] = merged_reject_by_source
        row_reject_reasons["_by_field"] = merged_reject_by_field

        run.raw_row_count = total_raw_rows
        run.normalized_row_count = total_inserted_rows
        run.duration_ms = latency_ms
        run.parse_success_rate = parse_success_rate
        run.schema_drift_count = schema_drift_count
        run.duplicate_key_count = duplicate_key_count
        run.rejected_row_count = rejected_row_count
        run.missing_required_count = missing_required_count
        run.row_reject_reasons_json = row_reject_reasons

        for snapshot_id in snapshot_ids:
            alert_eval = evaluate_alert_rules_for_snapshot(db, snapshot_id=snapshot_id)
            created_alert_count += alert_eval.created_alerts
            deduped_alert_count += alert_eval.deduped_alerts
        run.created_alert_count = created_alert_count
        run.deduped_alert_count = deduped_alert_count

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        update_source_health_state(
            db,
            source=source,
            status="completed",
            latency_ms=latency_ms,
            error_message=None,
        )
        record_source_health_snapshot(
            db,
            source=source,
            status="completed",
            latency_ms=latency_ms,
            parse_success_rate=parse_success_rate,
            schema_drift_count=schema_drift_count,
        )
    except Exception as exc:
        db.rollback()
        run = db.execute(select(IngestionRun).where(IngestionRun.id == run.id)).scalar_one()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = str(exc)
        run.duration_ms = latency_ms
        run.parse_success_rate = parse_success_rate
        run.schema_drift_count = schema_drift_count
        run.duplicate_key_count = duplicate_key_count
        run.rejected_row_count = rejected_row_count
        run.missing_required_count = missing_required_count
        run.row_reject_reasons_json = row_reject_reasons
        run.created_alert_count = created_alert_count
        run.deduped_alert_count = deduped_alert_count
        db.commit()
        db.refresh(run)
        update_source_health_state(
            db,
            source=source,
            status="failed",
            latency_ms=latency_ms,
            error_message=str(exc),
        )
        record_source_health_snapshot(
            db,
            source=source,
            status="failed",
            latency_ms=latency_ms,
            parse_success_rate=parse_success_rate,
            schema_drift_count=max(schema_drift_count, 1),
        )

    return SourceFileIngestionResult(
        run_id=run.id,
        source_id=source.id,
        source_name=run.source_name,
        source_identifier=run.source_identifier,
        status=run.status,
        trigger_type=run.trigger_type,
        attempt_number=int(run.attempt_number),
        max_attempts=int(run.max_attempts),
        raw_row_count=run.raw_row_count,
        normalized_row_count=run.normalized_row_count,
        created_alert_count=created_alert_count,
        deduped_alert_count=deduped_alert_count,
        duplicate_key_count=run.duplicate_key_count or 0,
        rejected_row_count=run.rejected_row_count or 0,
        missing_required_count=run.missing_required_count or 0,
        parse_success_rate=float(run.parse_success_rate) if run.parse_success_rate is not None else None,
        row_reject_reasons=run.row_reject_reasons_json,
        error_message=run.error_message,
    )


def reprocess_latest_file_source(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    source_file_path_override: str | None = None,
) -> tuple[FileSourceReprocessTarget, SourceFileIngestionResult]:
    target = get_latest_file_reprocess_target(
        db,
        org_id=org_id,
        source_id=source_id,
        source_file_path_override=source_file_path_override,
    )
    result = ingest_source_file(
        db,
        source_file_path=target.source_file_path,
        source_name=target.source_name,
        source_id=target.source_id,
        commodity_id=target.commodity_id,
        trigger_type="manual",
        attempt_number=1,
        max_attempts=1,
    )
    return target, result


def get_latest_file_reprocess_target(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    source_file_path_override: str | None = None,
) -> FileSourceReprocessTarget:
    latest_snapshot = _get_latest_file_snapshot(db, org_id=org_id, source_id=source_id)
    if latest_snapshot is None:
        raise ValueError("No file-source snapshot found for this organization")

    snapshot, source = latest_snapshot
    source_file_path = _source_file_path_for_reprocess(
        snapshot.raw_payload_json,
        source.url,
        source_file_path_override=source_file_path_override or settings.reprocess_source_file_path_override,
    )
    if not source_file_path:
        raise ValueError("Latest file-source snapshot has no reusable file path")

    return FileSourceReprocessTarget(
        source_id=source.id,
        source_name=source.name,
        commodity_id=snapshot.commodity_id,
        snapshot_id=snapshot.id,
        captured_at=snapshot.captured_at,
        source_file_path=source_file_path,
    )


def run_scheduled_file_ingestion_cycle(
    db: Session,
    *,
    commodity_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
    max_attempts: int | None = None,
    source_ids: list[uuid.UUID] | None = None,
) -> list[SourceFileIngestionResult]:
    attempts = max(1, max_attempts or settings.file_ingestion_max_attempts)
    sources = _list_file_sources(db, org_id=org_id, source_ids=source_ids)
    results: list[SourceFileIngestionResult] = []
    for source in sources:
        if not source.url:
            results.append(_record_missing_source_path_failure(db, source=source, max_attempts=attempts))
            continue

        final_result: SourceFileIngestionResult | None = None
        for attempt in range(1, attempts + 1):
            final_result = ingest_source_file(
                db,
                source_file_path=source.url,
                source_name=source.name,
                source_id=source.id,
                commodity_id=commodity_id,
                trigger_type="scheduled",
                attempt_number=attempt,
                max_attempts=attempts,
            )
            if final_result.status == "completed":
                break
            if attempt < attempts:
                time.sleep(min(10, attempt * 2))
        if final_result:
            results.append(final_result)
    return results


def _record_missing_source_path_failure(
    db: Session,
    *,
    source: Source,
    max_attempts: int,
) -> SourceFileIngestionResult:
    now = datetime.now(timezone.utc)
    error_message = "source.url is empty for file source"
    run = IngestionRun(
        source_name=source.name,
        source_identifier="",
        started_at=now,
        completed_at=now,
        status="failed",
        trigger_type="scheduled",
        attempt_number=1,
        max_attempts=max_attempts,
        raw_row_count=0,
        normalized_row_count=0,
        created_alert_count=0,
        deduped_alert_count=0,
        duplicate_key_count=0,
        rejected_row_count=0,
        missing_required_count=0,
        parse_success_rate=None,
        schema_drift_count=0,
        row_reject_reasons_json={"missing_source_file_path": 1},
        duration_ms=0,
        error_message=error_message,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    update_source_health_state(
        db,
        source=source,
        status="failed",
        latency_ms=0,
        error_message=error_message,
    )
    record_source_health_snapshot(
        db,
        source=source,
        status="failed",
        latency_ms=0,
        parse_success_rate=None,
        schema_drift_count=1,
    )
    return SourceFileIngestionResult(
        run_id=run.id,
        source_id=source.id,
        source_name=run.source_name,
        source_identifier=run.source_identifier,
        status=run.status,
        trigger_type=run.trigger_type,
        attempt_number=int(run.attempt_number),
        max_attempts=int(run.max_attempts),
        raw_row_count=run.raw_row_count,
        normalized_row_count=run.normalized_row_count,
        created_alert_count=run.created_alert_count or 0,
        deduped_alert_count=run.deduped_alert_count or 0,
        duplicate_key_count=run.duplicate_key_count or 0,
        rejected_row_count=run.rejected_row_count or 0,
        missing_required_count=run.missing_required_count or 0,
        parse_success_rate=float(run.parse_success_rate) if run.parse_success_rate is not None else None,
        row_reject_reasons=run.row_reject_reasons_json,
        error_message=run.error_message,
    )


def list_ingestion_runs(
    db: Session,
    *,
    limit: int = 25,
    org_id: uuid.UUID | None = None,
) -> list[IngestionRun]:
    query = select(IngestionRun)
    if org_id is not None:
        source_names = db.execute(
            select(Source.name).where(Source.org_id == org_id)
        ).scalars().all()
        if not source_names:
            return []
        query = query.where(IngestionRun.source_name.in_(source_names))
    return db.execute(
        query.order_by(desc(IngestionRun.started_at)).limit(limit)
    ).scalars().all()


def _get_latest_file_snapshot(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
) -> tuple[PriceSnapshot, Source] | None:
    query = (
        select(PriceSnapshot, Source)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(
            Source.org_id == org_id,
            Source.source_type == "file",
        )
    )
    if source_id is not None:
        query = query.where(Source.id == source_id)
    query = query.order_by(desc(PriceSnapshot.captured_at), desc(PriceSnapshot.id)).limit(1)
    return db.execute(query).one_or_none()


def _source_file_path_for_reprocess(
    raw_payload_json: dict | None,
    source_url: str | None,
    *,
    source_file_path_override: str | None = None,
) -> str:
    override = str(source_file_path_override or "").strip()
    if override:
        return override
    if isinstance(raw_payload_json, dict):
        payload_path = raw_payload_json.get("source_file_path")
        if payload_path is not None and str(payload_path).strip():
            return str(payload_path).strip()
    return str(source_url or "").strip()


def _list_file_sources(
    db: Session,
    *,
    org_id: uuid.UUID | None = None,
    source_ids: list[uuid.UUID] | None = None,
) -> list[Source]:
    query = select(Source).where(Source.is_active.is_(True), Source.source_type == "file")
    if org_id is not None:
        query = query.where(Source.org_id == org_id)
    if source_ids:
        query = query.where(Source.id.in_(source_ids))
    return db.execute(query.order_by(Source.name.asc())).scalars().all()
