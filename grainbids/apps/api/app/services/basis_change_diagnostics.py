from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_commodity_name, canonical_location_name, normalize_text
from app.services.price_comparison import CARRY_WINDOW


def build_basis_change_diagnostics(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    limit: int = 25,
    min_snapshot_rows: int = 25,
) -> dict[str, object]:
    latest_snapshot = _get_latest_snapshot(
        db,
        org_id=org_id,
        source_id=source_id,
        min_snapshot_rows=max(1, int(min_snapshot_rows)),
    )
    if latest_snapshot is None:
        return {
            "latest_snapshot": None,
            "summary": {
                "carry_window_hours": int(CARRY_WINDOW.total_seconds() // 3600),
                "row_count": 0,
            },
            "rows": [],
        }

    snapshot, source = latest_snapshot
    rows = _load_snapshot_rows(db, snapshot_id=snapshot.id)
    captured_at = snapshot.captured_at or datetime.now(timezone.utc)
    summary, sample_rows = summarize_basis_change_rows(
        rows,
        captured_at=captured_at,
        limit=limit,
    )

    return {
        "latest_snapshot": {
            "id": str(snapshot.id),
            "source_id": str(source.id),
            "source_name": source.name,
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
            "row_count": len(rows),
        },
        "summary": summary,
        "rows": sample_rows,
    }


def summarize_basis_change_rows(
    rows: list[NormalizedPrice],
    *,
    captured_at: datetime,
    limit: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    strict_non_zero_count = 0
    carried_non_zero_count = 0
    carried_without_strict_count = 0
    strict_without_carried_count = 0
    strict_vs_carried_value_mismatch_count = 0
    stale_non_zero_carried_count = 0
    rows_with_basis_last_changed_at = 0

    captured_at_utc = _to_utc(captured_at)
    diagnostics_rows: list[dict[str, object]] = []

    for row in rows:
        strict = _to_decimal(row.basis_change_strict)
        carried = _to_decimal(row.basis_change)
        strict_non_zero = strict is not None and strict != 0
        carried_non_zero = carried is not None and carried != 0
        if strict_non_zero:
            strict_non_zero_count += 1
        if carried_non_zero:
            carried_non_zero_count += 1

        row_carried_without_strict = carried_non_zero and not strict_non_zero
        row_strict_without_carried = strict_non_zero and not carried_non_zero
        row_value_mismatch = strict_non_zero and carried_non_zero and strict != carried

        if row_carried_without_strict:
            carried_without_strict_count += 1
        if row_strict_without_carried:
            strict_without_carried_count += 1
        if row_value_mismatch:
            strict_vs_carried_value_mismatch_count += 1

        age_hours: float | None = None
        stale_non_zero = False
        if row.basis_last_changed_at is not None:
            rows_with_basis_last_changed_at += 1
            age_seconds = (captured_at_utc - _to_utc(row.basis_last_changed_at)).total_seconds()
            age_hours = max(0.0, age_seconds / 3600.0)
            if carried_non_zero and age_seconds > CARRY_WINDOW.total_seconds():
                stale_non_zero = True
                stale_non_zero_carried_count += 1

        has_mismatch = row_carried_without_strict or row_strict_without_carried or row_value_mismatch
        if has_mismatch or stale_non_zero:
            diagnostics_rows.append(
                {
                    "location": canonical_location_name(row.location) or "-",
                    "commodity_name": canonical_commodity_name(row.commodity_name) or "-",
                    "delivery_label": _delivery_label(row),
                    "futures_month": normalize_text(row.futures_month),
                    "source_name": normalize_text(row.source_name),
                    "basis": _to_float(row.basis),
                    "basis_change": _to_float(carried),
                    "basis_change_strict": _to_float(strict),
                    "basis_change_diff": _to_float(_diff(carried, strict)),
                    "basis_last_changed_at": row.basis_last_changed_at.isoformat() if row.basis_last_changed_at else None,
                    "basis_last_changed_age_hours": round(age_hours, 2) if age_hours is not None else None,
                    "is_stale_non_zero": stale_non_zero,
                    "composite_key": row.composite_key,
                }
            )

    diagnostics_rows.sort(
        key=lambda item: (
            item["is_stale_non_zero"] is not True,
            -(abs(float(item["basis_change_diff"])) if item["basis_change_diff"] is not None else 0.0),
            str(item["location"]).casefold(),
            str(item["commodity_name"]).casefold(),
        )
    )

    summary = {
        "carry_window_hours": int(CARRY_WINDOW.total_seconds() // 3600),
        "row_count": len(rows),
        "strict_non_zero_count": strict_non_zero_count,
        "carried_non_zero_count": carried_non_zero_count,
        "carried_without_strict_count": carried_without_strict_count,
        "strict_without_carried_count": strict_without_carried_count,
        "strict_vs_carried_value_mismatch_count": strict_vs_carried_value_mismatch_count,
        "stale_non_zero_carried_count": stale_non_zero_carried_count,
        "rows_with_basis_last_changed_at": rows_with_basis_last_changed_at,
    }
    return summary, diagnostics_rows[: max(1, limit)]


def _get_latest_snapshot(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None,
    min_snapshot_rows: int,
) -> tuple[PriceSnapshot, Source] | None:
    # Prefer latest snapshot with a meaningful row count to avoid tiny tail snapshots.
    threshold_query = (
        select(PriceSnapshot, Source)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .join(NormalizedPrice, NormalizedPrice.snapshot_id == PriceSnapshot.id)
        .where(Source.org_id == org_id)
        .group_by(PriceSnapshot.id, Source.id)
        .having(func.count(NormalizedPrice.id) >= min_snapshot_rows)
    )
    if source_id is not None:
        threshold_query = threshold_query.where(Source.id == source_id)
    threshold_match = db.execute(
        threshold_query.order_by(desc(PriceSnapshot.captured_at), desc(PriceSnapshot.id)).limit(1)
    ).one_or_none()
    if threshold_match is not None:
        return threshold_match

    # Otherwise prefer latest snapshot that has any normalized rows.
    non_empty_query = (
        select(PriceSnapshot, Source)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .join(NormalizedPrice, NormalizedPrice.snapshot_id == PriceSnapshot.id)
        .where(Source.org_id == org_id)
    )
    if source_id is not None:
        non_empty_query = non_empty_query.where(Source.id == source_id)
    with_rows = db.execute(
        non_empty_query.order_by(desc(PriceSnapshot.captured_at), desc(PriceSnapshot.id)).limit(1)
    ).one_or_none()
    if with_rows is not None:
        return with_rows

    # Fallback when no normalized rows exist for this source yet.
    fallback_query = select(PriceSnapshot, Source).join(Source, Source.id == PriceSnapshot.source_id).where(Source.org_id == org_id)
    if source_id is not None:
        fallback_query = fallback_query.where(Source.id == source_id)
    return db.execute(fallback_query.order_by(desc(PriceSnapshot.captured_at), desc(PriceSnapshot.id)).limit(1)).one_or_none()


def _load_snapshot_rows(
    db: Session,
    *,
    snapshot_id: uuid.UUID,
) -> list[NormalizedPrice]:
    return db.execute(select(NormalizedPrice).where(NormalizedPrice.snapshot_id == snapshot_id)).scalars().all()


def _delivery_label(row: NormalizedPrice) -> str | None:
    return normalize_text(row.delivery_label or row.delivery_end or row.delivery_start)


def _to_decimal(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    decimal = Decimal(str(value))
    return decimal if decimal.is_finite() else None


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _diff(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None:
        return None
    return current - previous


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
