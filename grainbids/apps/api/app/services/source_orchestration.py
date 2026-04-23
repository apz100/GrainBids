from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import io
import time
import uuid

import pandas as pd
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.models.commodity import Commodity
from app.models.ingestion_run import IngestionRun
from app.models.source import Source
from app.models.source_health_snapshot import SourceHealthSnapshot
from app.services.alert_evaluator import evaluate_alert_rules_for_snapshot
from app.services.source_registry import fetch_with_adapter, get_adapter, list_adapters
from app.services.upload_csv import process_csv_upload


@dataclass
class RefreshExecutionResult:
    source_id: uuid.UUID
    source_name: str
    status: str
    attempts: int
    duration_ms: int | None
    row_count: int | None
    created_alert_count: int
    deduped_alert_count: int
    error_message: str | None


def run_source_refresh(
    db: Session,
    *,
    source: Source,
    commodity_id: uuid.UUID,
    trigger_type: str = "manual",
) -> RefreshExecutionResult:
    adapter = get_adapter(source.adapter_key or source.name.strip().lower())
    max_attempts = max(1, source.max_retries + 1)
    timeout_seconds = max(15, source.timeout_seconds)
    backoff_seconds = 2
    last_error: str | None = None
    duration_ms: int | None = None
    row_count: int | None = None
    created_alert_count = 0
    deduped_alert_count = 0

    for attempt in range(1, max_attempts + 1):
        run = IngestionRun(
            source_name=source.name,
            source_identifier=adapter.key,
            trigger_type=trigger_type,
            attempt_number=attempt,
            max_attempts=max_attempts,
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        started = time.perf_counter()
        status = "failed"
        schema_drift_count = 0
        parse_success_rate = 1.0
        try:
            df = _fetch_with_timeout(adapter.key, timeout_seconds=timeout_seconds)
            duration_ms = int((time.perf_counter() - started) * 1000)
            row_count = int(len(df.index))
            if row_count == 0:
                raise ValueError("source returned no rows")

            headers = [str(col) for col in df.columns.tolist()]
            rows = df.to_dict(orient="records")
            normalized_headers = {header.strip().lower() for header in headers}
            required = {"location", "commodity"}
            if not required.issubset(normalized_headers):
                schema_drift_count = 1
                parse_success_rate = 0.0

            upload = process_csv_upload(
                db,
                source_id=source.id,
                commodity_id=commodity_id,
                file_name=f"{adapter.key}_{datetime.now(timezone.utc).date()}.csv",
                content_type="text/csv",
                payload=_to_csv_bytes(rows, headers),
            )
            alert_eval = evaluate_alert_rules_for_snapshot(db, snapshot_id=upload.snapshot_id)
            created_alert_count = alert_eval.created_alerts
            deduped_alert_count = alert_eval.deduped_alerts
            status = "completed"
            run.raw_row_count = row_count
            run.normalized_row_count = upload.inserted_rows
            run.created_alert_count = created_alert_count
            run.deduped_alert_count = deduped_alert_count
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            status = "failed"
            parse_success_rate = 0.0
            schema_drift_count = max(schema_drift_count, 1)

        run.status = status
        run.duration_ms = duration_ms
        run.parse_success_rate = parse_success_rate
        run.schema_drift_count = schema_drift_count
        run.error_message = last_error if status == "failed" else None
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

        _update_source_state(
            db,
            source=source,
            status=status,
            latency_ms=duration_ms,
            error_message=last_error if status == "failed" else None,
        )
        _record_health_snapshot(
            db,
            source=source,
            status=status,
            latency_ms=duration_ms,
            parse_success_rate=parse_success_rate,
            schema_drift_count=schema_drift_count,
        )

        if status == "completed":
            return RefreshExecutionResult(
                source_id=source.id,
                source_name=source.name,
                status="completed",
                attempts=attempt,
                duration_ms=duration_ms,
                row_count=row_count,
                created_alert_count=created_alert_count,
                deduped_alert_count=deduped_alert_count,
                error_message=None,
            )

        if attempt < max_attempts:
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 30)

    return RefreshExecutionResult(
        source_id=source.id,
        source_name=source.name,
        status="failed",
        attempts=max_attempts,
        duration_ms=duration_ms,
        row_count=row_count,
        created_alert_count=created_alert_count,
        deduped_alert_count=deduped_alert_count,
        error_message=last_error,
    )


def list_sources_with_health(db: Session, *, org_id: uuid.UUID | None = None) -> list[dict]:
    query = select(Source).order_by(Source.name.asc())
    if org_id is not None:
        query = query.where(Source.org_id == org_id)
    rows = db.execute(query).scalars().all()
    now = datetime.now(timezone.utc)
    output: list[dict] = []
    for source in rows:
        stale_age_minutes = _minutes_since(source.last_success_at, now)
        poll_minutes = source.polling_interval_minutes or 15
        is_stale = stale_age_minutes is None or stale_age_minutes > poll_minutes * 2
        output.append(
            {
                "id": str(source.id),
                "name": source.name,
                "adapter_key": source.adapter_key,
                "source_type": source.source_type,
                "region": source.region,
                "is_active": source.is_active,
                "polling_interval_minutes": source.polling_interval_minutes,
                "timeout_seconds": source.timeout_seconds,
                "max_retries": source.max_retries,
                "last_polled_at": source.last_polled_at.isoformat() if source.last_polled_at else None,
                "last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
                "last_error_at": source.last_error_at.isoformat() if source.last_error_at else None,
                "consecutive_failures": source.consecutive_failures,
                "latest_error_message": source.latest_error_message,
                "ingestion_latency_ms": source.last_ingestion_latency_ms,
                "stale_age_minutes": stale_age_minutes,
                "is_stale": is_stale,
                "confidence_score": float(source.confidence_score) if source.confidence_score is not None else None,
            }
        )
    return output


def build_sla_summary(db: Session, *, org_id: uuid.UUID | None = None) -> dict:
    now = datetime.now(timezone.utc)
    source_query = select(Source).where(Source.is_active.is_(True))
    if org_id is not None:
        source_query = source_query.where(Source.org_id == org_id)
    sources = db.execute(source_query).scalars().all()
    source_rows = list_sources_with_health(db, org_id=org_id)
    fresh = sum(1 for row in source_rows if row["is_active"] and not row["is_stale"])
    stale = sum(1 for row in source_rows if row["is_active"] and row["is_stale"])
    failing = sum(1 for row in source_rows if row["is_active"] and int(row["consecutive_failures"] or 0) > 0)
    failing_sources = [
        {
            "id": row["id"],
            "name": row["name"],
            "consecutive_failures": row["consecutive_failures"],
            "latest_error_message": row["latest_error_message"],
        }
        for row in source_rows
        if row["is_active"] and int(row["consecutive_failures"] or 0) > 0
    ]

    run_query = select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(1)
    if org_id is not None:
        run_query = (
            select(IngestionRun)
            .join(Source, Source.name == IngestionRun.source_name)
            .where(Source.org_id == org_id)
            .order_by(desc(IngestionRun.started_at))
            .limit(1)
        )
    last_run = db.execute(run_query).scalar_one_or_none()

    return {
        "generated_at": now.isoformat(),
        "active_sources": len(sources),
        "fresh_sources": fresh,
        "stale_sources": stale,
        "failing_sources": failing,
        "last_ingestion_run": {
            "id": str(last_run.id),
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
            "completed_at": last_run.completed_at.isoformat() if last_run.completed_at else None,
        } if last_run else None,
        "failing_source_rows": failing_sources,
    }


def list_due_sources(db: Session, *, now: datetime | None = None) -> list[Source]:
    current = now or datetime.now(timezone.utc)
    return db.execute(
        select(Source).where(
            and_(
                Source.is_active.is_(True),
                (Source.next_poll_at.is_(None) | (Source.next_poll_at <= current)),
            )
        )
    ).scalars().all()


def poll_due_sources(
    db: Session,
    *,
    commodity_id: uuid.UUID,
    now: datetime | None = None,
) -> list[RefreshExecutionResult]:
    results: list[RefreshExecutionResult] = []
    for source in list_due_sources(db, now=now):
        results.append(
            run_source_refresh(
                db,
                source=source,
                commodity_id=commodity_id,
                trigger_type="scheduled",
            )
        )
    return results


def _fetch_with_timeout(adapter_key: str, *, timeout_seconds: int) -> pd.DataFrame:
    adapter = get_adapter(adapter_key)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_with_adapter, adapter)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            raise TimeoutError(f"source fetch timed out after {timeout_seconds}s") from exc


def _to_csv_bytes(rows: list[dict], headers: list[str]) -> bytes:
    buffer = io.StringIO()
    if not headers:
        return b""
    import csv

    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _update_source_state(
    db: Session,
    *,
    source: Source,
    status: str,
    latency_ms: int | None,
    error_message: str | None,
) -> None:
    now = datetime.now(timezone.utc)
    source.last_polled_at = now
    source.next_poll_at = now + timedelta(minutes=source.polling_interval_minutes or 15)
    source.last_ingestion_latency_ms = latency_ms

    if status == "completed":
        source.last_success_at = now
        source.consecutive_failures = 0
        source.latest_error_message = None
    else:
        source.last_error_at = now
        source.consecutive_failures = int(source.consecutive_failures or 0) + 1
        source.latest_error_message = error_message

    source.confidence_score = _compute_confidence(source)
    db.add(source)
    db.commit()
    db.refresh(source)


def _record_health_snapshot(
    db: Session,
    *,
    source: Source,
    status: str,
    latency_ms: int | None,
    parse_success_rate: float,
    schema_drift_count: int,
) -> None:
    now = datetime.now(timezone.utc)
    stale_age = _minutes_since(source.last_success_at, now)
    snapshot = SourceHealthSnapshot(
        source_id=source.id,
        ingestion_latency_ms=latency_ms,
        parse_success_rate=parse_success_rate,
        stale_age_minutes=stale_age,
        schema_drift_incidents=schema_drift_count,
        confidence_score=source.confidence_score,
        status=status,
    )
    db.add(snapshot)
    db.commit()


def _compute_confidence(source: Source) -> float:
    score = 1.0
    failures = int(source.consecutive_failures or 0)
    score -= min(0.6, failures * 0.15)
    if source.last_ingestion_latency_ms and source.last_ingestion_latency_ms > 60000:
        score -= 0.1
    return max(0.0, round(score, 3))


def _minutes_since(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    delta = now - value
    return max(0, int(delta.total_seconds() // 60))


def seed_sources_from_registry(db: Session, *, org_id: uuid.UUID) -> int:
    existing_names = {
        (source.adapter_key or source.name.strip().lower())
        for source in db.execute(select(Source).where(Source.org_id == org_id)).scalars().all()
    }
    created = 0
    for adapter in list_adapters():
        if adapter.key in existing_names:
            continue
        source = Source(
            org_id=org_id,
            name=adapter.key,
            adapter_key=adapter.key,
            source_type="automated",
            polling_interval_minutes=adapter.default_poll_minutes,
            timeout_seconds=adapter.default_timeout_seconds,
            max_retries=2,
            is_active=True,
        )
        db.add(source)
        created += 1
    if created:
        db.commit()
    return created
