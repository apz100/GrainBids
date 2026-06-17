from __future__ import annotations

from multiprocessing import get_context
import queue
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import time
import uuid

import pandas as pd
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.models.commodity import Commodity
from app.models.ingestion_run import IngestionRun
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.alert_evaluator import evaluate_alert_rules_for_snapshot
from app.services.alert_notifier import notify_new_alerts
from app.services.source_health import minutes_since, record_source_health_snapshot, update_source_health_state
from app.services.source_registry import fetch_with_adapter, get_adapter, list_adapters, list_pilot_adapter_keys
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
        print(
            f"[SOURCE] start name={source.name} adapter={adapter.key} "
            f"attempt={attempt}/{max_attempts} timeout={timeout_seconds}s"
        )
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
        parse_success_rate: float | None = 0.0
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
            parse_success_rate = upload.parse_success_rate
            alert_eval = evaluate_alert_rules_for_snapshot(db, snapshot_id=upload.snapshot_id)
            created_alert_count = alert_eval.created_alerts
            deduped_alert_count = alert_eval.deduped_alerts
            if alert_eval.created_alert_ids:
                notify_new_alerts(db, alert_ids=alert_eval.created_alert_ids)
            status = "completed"
            run.raw_row_count = row_count
            run.normalized_row_count = upload.inserted_rows
            run.created_alert_count = created_alert_count
            run.deduped_alert_count = deduped_alert_count
            run.duplicate_key_count = upload.duplicate_key_count
            run.rejected_row_count = upload.rejected_row_count
            run.missing_required_count = upload.missing_required_count
            run.row_reject_reasons_json = upload.row_reject_reasons
            print(
                f"[SOURCE] done name={source.name} adapter={adapter.key} status=completed "
                f"rows={row_count} inserted={upload.inserted_rows} duration_ms={duration_ms}"
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.execute(select(IngestionRun).where(IngestionRun.id == run.id)).scalar_one()
            last_error = str(exc)
            status = "failed"
            parse_success_rate = 0.0
            schema_drift_count = max(schema_drift_count, 1)
            print(
                f"[SOURCE] fail name={source.name} adapter={adapter.key} "
                f"attempt={attempt}/{max_attempts} error={last_error}"
            )

        run.status = status
        run.duration_ms = duration_ms
        run.parse_success_rate = parse_success_rate
        run.schema_drift_count = schema_drift_count
        run.error_message = last_error if status == "failed" else None
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

        update_source_health_state(
            db,
            source=source,
            status=status,
            latency_ms=duration_ms,
            error_message=last_error if status == "failed" else None,
        )
        record_source_health_snapshot(
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


def list_sources_with_health(
    db: Session,
    *,
    org_id: uuid.UUID | None = None,
    include_logical_file_sources: bool = True,
) -> list[dict]:
    query = select(Source).order_by(Source.name.asc())
    if org_id is not None:
        query = query.where(Source.org_id == org_id)
    rows = db.execute(query).scalars().all()
    now = datetime.now(timezone.utc)
    latest_run_by_source = _load_latest_run_by_source_name(db, org_id=org_id)
    success_run_counts = _load_completed_run_counts(db, org_id=org_id)
    pilot_keys = set(list_pilot_adapter_keys())
    output: list[dict] = []
    for source in rows:
        stale_age_minutes = minutes_since(source.last_success_at, now)
        poll_minutes = source.polling_interval_minutes or 15
        is_stale = stale_age_minutes is None or stale_age_minutes > poll_minutes * 2
        latest_run = latest_run_by_source.get(source.name)
        successful_run_count = int(success_run_counts.get(source.name, 0))
        promotion_status = _promotion_status(
            source=source,
            successful_run_count=successful_run_count,
            pilot_keys=pilot_keys,
        )
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
                "latest_run_status": latest_run.status if latest_run else None,
                "latest_parse_success_rate": float(latest_run.parse_success_rate) if latest_run and latest_run.parse_success_rate is not None else None,
                "latest_schema_drift_count": latest_run.schema_drift_count if latest_run else None,
                "latest_duplicate_key_count": latest_run.duplicate_key_count if latest_run else None,
                "latest_rejected_row_count": latest_run.rejected_row_count if latest_run else None,
                "latest_missing_required_count": latest_run.missing_required_count if latest_run else None,
                "latest_row_reject_reasons": latest_run.row_reject_reasons_json if latest_run else None,
                "successful_run_count": successful_run_count,
                "promotion_status": promotion_status,
                "can_refresh": source.source_type == "automated",
            }
        )
    if include_logical_file_sources:
        output.extend(_build_file_logical_source_rows(db, rows=rows, now=now))
    return output


def build_sla_summary(db: Session, *, org_id: uuid.UUID | None = None) -> dict:
    now = datetime.now(timezone.utc)
    source_query = select(Source).where(Source.is_active.is_(True))
    if org_id is not None:
        source_query = source_query.where(Source.org_id == org_id)
    sources = db.execute(source_query).scalars().all()
    source_rows = list_sources_with_health(db, org_id=org_id, include_logical_file_sources=False)
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
    success_query = (
        select(IngestionRun)
        .where(IngestionRun.status == "completed")
        .order_by(desc(IngestionRun.started_at))
        .limit(1)
    )
    if org_id is not None:
        source_names = db.execute(select(Source.name).where(Source.org_id == org_id)).scalars().all()
        if source_names:
            success_query = success_query.where(IngestionRun.source_name.in_(source_names))
        else:
            success_query = success_query.where(IngestionRun.id.is_(None))
    last_successful_run = db.execute(success_query).scalar_one_or_none()

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
        "last_successful_ingestion_run": {
            "id": str(last_successful_run.id),
            "status": last_successful_run.status,
            "started_at": last_successful_run.started_at.isoformat() if last_successful_run.started_at else None,
            "completed_at": last_successful_run.completed_at.isoformat() if last_successful_run.completed_at else None,
        } if last_successful_run else None,
        "failing_source_rows": failing_sources,
    }


def list_due_sources(db: Session, *, now: datetime | None = None) -> list[Source]:
    current = now or datetime.now(timezone.utc)
    pilot_keys = list_pilot_adapter_keys()
    return db.execute(
        select(Source).where(
            and_(
                Source.is_active.is_(True),
                Source.source_type == "automated",
                Source.adapter_key.in_(pilot_keys),
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
    due_sources = list_due_sources(db, now=now)
    print(f"[POLL] due_sources={len(due_sources)}")
    for index, source in enumerate(due_sources, start=1):
        print(
            f"[POLL] source={index}/{len(due_sources)} "
            f"name={source.name} adapter={source.adapter_key or source.name.strip().lower()}"
        )
        result = run_source_refresh(
            db,
            source=source,
            commodity_id=commodity_id,
            trigger_type="scheduled",
        )
        results.append(result)
        print(
            f"[POLL] source_done name={result.source_name} status={result.status} "
            f"attempts={result.attempts} duration_ms={result.duration_ms} rows={result.row_count}"
        )
    print(f"[POLL] complete sources={len(results)} failures={sum(1 for r in results if r.status != 'completed')}")
    return results


def _fetch_with_timeout(adapter_key: str, *, timeout_seconds: int) -> pd.DataFrame:
    adapter = get_adapter(adapter_key)
    ctx = get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_fetch_with_timeout_worker, args=(result_queue, adapter), daemon=True)
    process.start()
    try:
        try:
            status, payload = result_queue.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            process.terminate()
            process.join(timeout=5)
            raise TimeoutError(f"source fetch timed out after {timeout_seconds}s") from exc

        process.join(timeout=5)
        if status == "ok":
            if isinstance(payload, pd.DataFrame):
                return payload
            raise TypeError(f"Unexpected payload type from source worker for {adapter.key}: {type(payload)!r}")
        raise RuntimeError(str(payload))
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)


def _fetch_with_timeout_worker(result_queue, adapter) -> None:
    try:
        df = fetch_with_adapter(adapter)
        result_queue.put(("ok", df))
    except Exception as exc:  # noqa: BLE001
        result_queue.put(("error", repr(exc)))


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


def seed_sources_from_registry(
    db: Session,
    *,
    org_id: uuid.UUID,
    adapter_keys: list[str] | None = None,
) -> int:
    existing_names = {
        (source.adapter_key or source.name.strip().lower())
        for source in db.execute(select(Source).where(Source.org_id == org_id)).scalars().all()
    }
    allowed = set(adapter_keys or [adapter.key for adapter in list_adapters()])
    created = 0
    for adapter in list_adapters():
        if adapter.key not in allowed:
            continue
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


def _load_latest_run_by_source_name(db: Session, *, org_id: uuid.UUID | None = None) -> dict[str, IngestionRun]:
    query = select(IngestionRun).order_by(desc(IngestionRun.started_at))
    if org_id is not None:
        source_names = db.execute(select(Source.name).where(Source.org_id == org_id)).scalars().all()
        if not source_names:
            return {}
        query = query.where(IngestionRun.source_name.in_(source_names))
    rows = db.execute(query.limit(2000)).scalars().all()
    latest: dict[str, IngestionRun] = {}
    for row in rows:
        latest.setdefault(row.source_name, row)
    return latest


def _load_completed_run_counts(db: Session, *, org_id: uuid.UUID | None = None) -> dict[str, int]:
    query = (
        select(IngestionRun.source_name, func.count(IngestionRun.id))
        .where(IngestionRun.status == "completed")
        .group_by(IngestionRun.source_name)
    )
    if org_id is not None:
        source_names = db.execute(select(Source.name).where(Source.org_id == org_id)).scalars().all()
        if not source_names:
            return {}
        query = query.where(IngestionRun.source_name.in_(source_names))
    return {name: int(count) for name, count in db.execute(query).all()}


def _promotion_status(*, source: Source, successful_run_count: int, pilot_keys: set[str]) -> str:
    adapter = (source.adapter_key or "").strip().lower()
    if source.source_type != "automated":
        return "n/a"
    if adapter not in pilot_keys:
        return "not_pilot"
    confidence = float(source.confidence_score) if source.confidence_score is not None else 0.0
    if successful_run_count >= 3 and confidence >= 0.8 and int(source.consecutive_failures or 0) == 0:
        return "promoted"
    if successful_run_count >= 1:
        return "pilot"
    return "pilot_pending"


def _build_file_logical_source_rows(
    db: Session,
    *,
    rows: list[Source],
    now: datetime,
) -> list[dict]:
    output: list[dict] = []
    for source in rows:
        if source.source_type != "file":
            continue
        latest_snapshot = db.execute(
            select(PriceSnapshot)
            .where(PriceSnapshot.source_id == source.id)
            .order_by(desc(PriceSnapshot.captured_at))
            .limit(1)
        ).scalar_one_or_none()
        if latest_snapshot is None:
            continue
        logical_groups = _logical_groups_for_snapshot(db, snapshot_id=latest_snapshot.id)
        for logical_name, group in logical_groups.items():
            stale_age_minutes = minutes_since(latest_snapshot.captured_at, now)
            poll_minutes = source.polling_interval_minutes or 15
            is_stale = stale_age_minutes is None or stale_age_minutes > poll_minutes * 2
            output.append(
                {
                    "id": f"{source.id}:{logical_name}",
                    "name": logical_name,
                    "adapter_key": source.adapter_key,
                    "source_type": "file_logical",
                    "region": source.region,
                    "is_active": source.is_active,
                    "polling_interval_minutes": source.polling_interval_minutes,
                    "timeout_seconds": source.timeout_seconds,
                    "max_retries": source.max_retries,
                    "last_polled_at": source.last_polled_at.isoformat() if source.last_polled_at else None,
                    "last_success_at": latest_snapshot.captured_at.isoformat() if latest_snapshot.captured_at else None,
                    "last_error_at": source.last_error_at.isoformat() if source.last_error_at else None,
                    "consecutive_failures": source.consecutive_failures,
                    "latest_error_message": source.latest_error_message,
                    "ingestion_latency_ms": source.last_ingestion_latency_ms,
                    "stale_age_minutes": stale_age_minutes,
                    "is_stale": is_stale,
                    "confidence_score": float(source.confidence_score) if source.confidence_score is not None else None,
                    "latest_run_status": "completed",
                    "latest_parse_success_rate": group["parse_success_rate"],
                    "latest_schema_drift_count": 0,
                    "latest_duplicate_key_count": group["duplicate_key_count"],
                    "latest_rejected_row_count": group["rejected_row_count"],
                    "latest_missing_required_count": group["missing_required_count"],
                    "latest_row_reject_reasons": group["row_reject_reasons"],
                    "successful_run_count": 1,
                    "promotion_status": "n/a",
                    "can_refresh": False,
                    "logical_parent_source_name": source.name,
                    "logical_row_count": group["row_count"],
                }
            )
    return output


def _logical_groups_for_snapshot(db: Session, *, snapshot_id: uuid.UUID) -> dict[str, dict]:
    rows = db.execute(
        select(NormalizedPrice).where(NormalizedPrice.snapshot_id == snapshot_id)
    ).scalars().all()
    grouped: dict[str, list[NormalizedPrice]] = {}
    for row in rows:
        key = (row.source_name or "").strip() or "Unknown"
        grouped.setdefault(key, []).append(row)

    output: dict[str, dict] = {}
    for key, group_rows in grouped.items():
        row_count = len(group_rows)
        duplicate_key_count = row_count - len({(row.composite_key or "").strip() for row in group_rows if row.composite_key})
        reject_reasons: dict[str, int] = {}
        missing_required_count = 0
        rejected_row_count = 0
        for row in group_rows:
            reasons = _logical_missing_reasons(row)
            if reasons:
                rejected_row_count += 1
                for reason in reasons:
                    reject_reasons[reason] = int(reject_reasons.get(reason, 0)) + 1
                    if reason.startswith("missing_"):
                        missing_required_count += 1
        parse_success_rate = float((row_count - rejected_row_count) / row_count) if row_count else 0.0
        output[key] = {
            "row_count": row_count,
            "duplicate_key_count": duplicate_key_count,
            "rejected_row_count": rejected_row_count,
            "missing_required_count": missing_required_count,
            "row_reject_reasons": reject_reasons,
            "parse_success_rate": parse_success_rate,
        }
    return output


def _logical_missing_reasons(row: NormalizedPrice) -> list[str]:
    reasons: list[str] = []
    if not (row.delivery_end or row.delivery_label):
        reasons.append("missing_delivery_window")
    if row.futures_month is None or str(row.futures_month).strip() == "":
        reasons.append("missing_futures_month")
    if row.basis is None:
        reasons.append("missing_basis")
    if row.cash_price_bu is None:
        reasons.append("missing_cash_price_bu")
    if row.cash_price_mt is None:
        reasons.append("missing_cash_price_mt")
    if row.composite_key is None or str(row.composite_key).strip() == "":
        reasons.append("missing_composite_key")
    return reasons
