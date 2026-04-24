from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.source import Source
from app.models.source_health_snapshot import SourceHealthSnapshot


def update_source_health_state(
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

    source.confidence_score = compute_confidence(source)
    db.add(source)
    db.commit()
    db.refresh(source)


def record_source_health_snapshot(
    db: Session,
    *,
    source: Source,
    status: str,
    latency_ms: int | None,
    parse_success_rate: float | None,
    schema_drift_count: int,
) -> None:
    now = datetime.now(timezone.utc)
    stale_age = minutes_since(source.last_success_at, now)
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


def compute_confidence(source: Source) -> float:
    score = 1.0
    failures = int(source.consecutive_failures or 0)
    score -= min(0.6, failures * 0.15)
    if source.last_ingestion_latency_ms and source.last_ingestion_latency_ms > 60000:
        score -= 0.1
    return max(0.0, round(score, 3))


def minutes_since(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    delta = now - value
    return max(0, int(delta.total_seconds() // 60))
