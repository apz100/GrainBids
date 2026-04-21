from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.normalized_price import NormalizedPrice


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
) -> None:
    if not normalized_rows:
        return

    prior_by_key = _load_most_recent_prior_rows(
        db,
        composite_keys={row.composite_key for row in normalized_rows},
        captured_at=captured_at,
    )

    for row in normalized_rows:
        prior = prior_by_key.get(row.composite_key)
        changes = calculate_price_changes(
            basis=row.basis,
            cash_price_bu=row.cash_price_bu,
            cash_price_mt=row.cash_price_mt,
            prior_basis=prior.basis if prior else None,
            prior_cash_price_bu=prior.cash_price_bu if prior else None,
            prior_cash_price_mt=prior.cash_price_mt if prior else None,
        )
        row.basis_change = changes.basis_change
        row.cash_price_bu_change = changes.cash_price_bu_change
        row.cash_price_mt_change = changes.cash_price_mt_change


@dataclass(frozen=True)
class PriceChanges:
    basis_change: Decimal | None
    cash_price_bu_change: Decimal | None
    cash_price_mt_change: Decimal | None


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


def select_most_recent_prior(candidates: list[tuple[object, datetime]]) -> object | None:
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[1])[0]


def _load_most_recent_prior_rows(
    db: "Session",
    *,
    composite_keys: set[str],
    captured_at: datetime,
) -> dict[str, Any]:
    from sqlalchemy import desc, select

    from app.models.normalized_price import NormalizedPrice
    from app.models.price_snapshot import PriceSnapshot

    if not composite_keys:
        return {}

    query = (
        select(NormalizedPrice, PriceSnapshot.captured_at)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .where(NormalizedPrice.composite_key.in_(composite_keys))
        .where(PriceSnapshot.captured_at < captured_at)
        .order_by(NormalizedPrice.composite_key, desc(PriceSnapshot.captured_at))
    )

    prior_by_key: dict[str, NormalizedPrice] = {}
    for row, _prior_captured_at in db.execute(query).all():
        if row.composite_key not in prior_by_key:
            prior_by_key[row.composite_key] = row
    return prior_by_key


def _delta(current: Decimal | float | int | None, prior: Decimal | float | int | None) -> Decimal | None:
    if current is None or prior is None:
        return None
    return Decimal(str(current)) - Decimal(str(prior))


def _normalize_key_part(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())
