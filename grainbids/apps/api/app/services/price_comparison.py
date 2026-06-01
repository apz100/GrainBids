from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
import uuid

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.normalized_price import NormalizedPrice

CARRY_WINDOW = timedelta(hours=24)
ZERO_DECIMAL = Decimal("0.0")


def build_composite_key(
    *,
    location: str | None,
    commodity_name: str | None,
    delivery_start: str | None,
    delivery_end: str | None,
    futures_month: str | None,
) -> str:
    parts = [location, commodity_name, delivery_start, delivery_end, futures_month]
    return "|".join(_normalize_key_part(part) for part in parts)


def apply_historical_changes(
    db: "Session",
    *,
    normalized_rows: list["NormalizedPrice"],
    captured_at: datetime,
    org_id: uuid.UUID | None = None,
) -> None:
    if not normalized_rows:
        return

    prior_day_by_key = _load_most_recent_prior_rows(
        db,
        composite_keys={row.composite_key for row in normalized_rows},
        captured_at=captured_at,
        org_id=org_id,
    )
    latest_prior_by_key = _load_latest_prior_rows(
        db,
        composite_keys={row.composite_key for row in normalized_rows},
        captured_at=captured_at,
        org_id=org_id,
    )

    for row in normalized_rows:
        prior_day = prior_day_by_key.get(row.composite_key)
        latest_prior = latest_prior_by_key.get(row.composite_key)
        changes = calculate_price_changes(
            basis=row.basis,
            cash_price_bu=row.cash_price_bu,
            cash_price_mt=row.cash_price_mt,
            prior_basis=prior_day.basis if prior_day else None,
            prior_cash_price_bu=prior_day.cash_price_bu if prior_day else None,
            prior_cash_price_mt=prior_day.cash_price_mt if prior_day else None,
        )
        basis_policy = calculate_basis_change_policy(
            basis=row.basis,
            captured_at=captured_at,
            prior_day_basis=prior_day.basis if prior_day else None,
            prior_run_basis=latest_prior.basis if latest_prior else None,
            prior_user_basis_change=latest_prior.basis_change if latest_prior else None,
            prior_basis_last_changed_at=latest_prior.basis_last_changed_at if latest_prior else None,
        )
        row.basis_change_strict = basis_policy.basis_change_strict
        row.basis_change = basis_policy.basis_change
        row.basis_last_changed_at = basis_policy.basis_last_changed_at
        row.cash_price_bu_change = changes.cash_price_bu_change
        row.cash_price_mt_change = changes.cash_price_mt_change


@dataclass(frozen=True)
class PriceChanges:
    basis_change: Decimal | None
    cash_price_bu_change: Decimal | None
    cash_price_mt_change: Decimal | None


@dataclass(frozen=True)
class BasisChangePolicy:
    basis_change_strict: Decimal | None
    basis_change: Decimal
    basis_last_changed_at: datetime | None


def calculate_price_changes(
    *,
    basis: Decimal | float | int | None,
    cash_price_bu: Decimal | float | int | None,
    cash_price_mt: Decimal | float | int | None,
    prior_basis: Decimal | float | int | None,
    prior_cash_price_bu: Decimal | float | int | None,
    prior_cash_price_mt: Decimal | float | int | None,
) -> PriceChanges:
    return PriceChanges(
        basis_change=_delta(basis, prior_basis),
        cash_price_bu_change=_delta(cash_price_bu, prior_cash_price_bu),
        cash_price_mt_change=_delta(cash_price_mt, prior_cash_price_mt),
    )


def calculate_basis_change_policy(
    *,
    basis: Decimal | float | int | None,
    captured_at: datetime,
    prior_day_basis: Decimal | float | int | None,
    prior_run_basis: Decimal | float | int | None,
    prior_user_basis_change: Decimal | float | int | None,
    prior_basis_last_changed_at: datetime | None,
) -> BasisChangePolicy:
    strict_change = _delta(basis, prior_day_basis)
    run_delta = _delta(basis, prior_run_basis)

    if run_delta is not None and run_delta != 0:
        return BasisChangePolicy(
            basis_change_strict=strict_change,
            basis_change=run_delta,
            basis_last_changed_at=captured_at,
        )

    prior_user_change = _to_decimal(prior_user_basis_change)
    if (
        run_delta is not None
        and run_delta == 0
        and prior_user_change is not None
        and prior_basis_last_changed_at is not None
        and _is_within_carry_window(captured_at, prior_basis_last_changed_at)
    ):
        return BasisChangePolicy(
            basis_change_strict=strict_change,
            basis_change=prior_user_change,
            basis_last_changed_at=prior_basis_last_changed_at,
        )

    return BasisChangePolicy(
        basis_change_strict=strict_change,
        basis_change=ZERO_DECIMAL,
        basis_last_changed_at=None,
    )


def select_most_recent_prior(candidates: list[tuple[object, datetime]]) -> object | None:
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[1])[0]


def _load_most_recent_prior_rows(
    db: "Session",
    *,
    composite_keys: set[str],
    captured_at: datetime,
    org_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    from sqlalchemy import desc, func, select

    from app.models.normalized_price import NormalizedPrice
    from app.models.price_snapshot import PriceSnapshot
    from app.models.source import Source

    if not composite_keys:
        return {}

    current_day = captured_at.date()
    prior_day_query = (
        select(func.max(func.date(PriceSnapshot.captured_at)))
        .join(NormalizedPrice, NormalizedPrice.snapshot_id == PriceSnapshot.id)
        .where(NormalizedPrice.composite_key.in_(composite_keys))
        .where(func.date(PriceSnapshot.captured_at) < current_day)
        # Treat weekend snapshots as non-trading for strict day-over-day.
        .where(func.extract("isodow", PriceSnapshot.captured_at).between(1, 5))
    )
    if org_id is not None:
        prior_day_query = (
            prior_day_query.join(Source, Source.id == PriceSnapshot.source_id)
            .where(Source.org_id == org_id)
        )
    prior_day = db.execute(prior_day_query).scalar_one_or_none()
    if prior_day is None:
        return {}

    query = (
        select(NormalizedPrice, PriceSnapshot.captured_at)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .where(NormalizedPrice.composite_key.in_(composite_keys))
        .where(func.date(PriceSnapshot.captured_at) == prior_day)
        .order_by(NormalizedPrice.composite_key, desc(PriceSnapshot.captured_at))
    )
    if org_id is not None:
        query = query.join(Source, Source.id == PriceSnapshot.source_id).where(Source.org_id == org_id)

    prior_by_key: dict[str, NormalizedPrice] = {}
    for row, _prior_captured_at in db.execute(query).all():
        if row.composite_key not in prior_by_key:
            prior_by_key[row.composite_key] = row
    return prior_by_key


def _load_latest_prior_rows(
    db: "Session",
    *,
    composite_keys: set[str],
    captured_at: datetime,
    org_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    from sqlalchemy import desc, func, or_, select

    from app.models.normalized_price import NormalizedPrice
    from app.models.price_snapshot import PriceSnapshot
    from app.models.source import Source

    if not composite_keys:
        return {}

    current_day = captured_at.date()
    query = (
        select(NormalizedPrice, PriceSnapshot.captured_at)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .where(NormalizedPrice.composite_key.in_(composite_keys))
        .where(PriceSnapshot.captured_at < captured_at)
        # Keep same-day prior runs for intraday updates, but otherwise only use
        # weekday snapshots so Monday compares against Friday (not weekend copies).
        .where(
            or_(
                func.date(PriceSnapshot.captured_at) == current_day,
                func.extract("isodow", PriceSnapshot.captured_at).between(1, 5),
            )
        )
        .order_by(NormalizedPrice.composite_key, desc(PriceSnapshot.captured_at))
    )
    if org_id is not None:
        query = query.join(Source, Source.id == PriceSnapshot.source_id).where(Source.org_id == org_id)

    prior_by_key: dict[str, NormalizedPrice] = {}
    for row, _prior_captured_at in db.execute(query).all():
        if row.composite_key not in prior_by_key:
            prior_by_key[row.composite_key] = row
    return prior_by_key


def _delta(current: Decimal | float | int | None, prior: Decimal | float | int | None) -> Decimal | None:
    if current is None or prior is None:
        return None
    return Decimal(str(current)) - Decimal(str(prior))


def _to_decimal(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    return parsed if parsed.is_finite() else None


def _is_within_carry_window(captured_at: datetime, basis_last_changed_at: datetime) -> bool:
    current = _to_utc(captured_at)
    previous = _to_utc(basis_last_changed_at)
    delta = current - previous
    return timedelta(0) <= delta <= CARRY_WINDOW


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_key_part(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())
