from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from app.models.normalized_price import NormalizedPrice
from app.services.canonical_resolver import _market_key_from_row, _rank_rows


def _build_row(
    *,
    source_name: str,
    commodity_name: str = "Corn",
    location: str = "Alliston",
    company_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    futures_month: str | None = "Jul 2026",
    futures_price: float | None = 479.25,
    basis: float | None = 1.4,
    cash_price_bu: float | None = 6.19,
    cash_price_mt: float | None = 243.79,
    delivery_end: str | None = "May 2026",
) -> NormalizedPrice:
    return NormalizedPrice(
        id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        company_id=company_id,
        location_id=location_id,
        location=location,
        commodity_name=commodity_name,
        source_name=source_name,
        delivery_start=None,
        delivery_end=delivery_end,
        delivery_label=delivery_end,
        futures_month=futures_month,
        futures_price=futures_price,
        basis=basis,
        cash_price_bu=cash_price_bu,
        cash_price_mt=cash_price_mt,
        basis_change=None,
        cash_price_bu_change=None,
        cash_price_mt_change=None,
        composite_key=f"{location}|{commodity_name}|{delivery_end}|{futures_month}",
        is_canonical=False,
        canonical_rank=None,
        canonical_reason=None,
    )


def test_market_key_uses_text_fallback_when_ids_missing() -> None:
    row = _build_row(source_name="GLG", company_id=None, location_id=None, location="Any Blenheim Branch Corn")
    key = _market_key_from_row(row)
    assert key[0] == "glg"
    assert key[1] == "blenheim branch"


def test_priority_rank_wins_when_configured() -> None:
    company_id = uuid.uuid4()
    row_glg = _build_row(source_name="GLG", company_id=company_id)
    row_agricharts = _build_row(source_name="Agricharts", company_id=company_id)
    now = datetime.now(timezone.utc)
    ranked = _rank_rows(
        [(row_glg, now), (row_agricharts, now)],
        priority_map={(company_id, "glg"): 1, (company_id, "agricharts"): 2},
        min_quality_score=0.8,
    )
    assert ranked[0][0].source_name == "GLG"


def test_completeness_wins_when_priority_absent() -> None:
    row_complete = _build_row(source_name="Agricharts")
    row_partial = _build_row(source_name="GLG", futures_price=None, cash_price_mt=None)
    now = datetime.now(timezone.utc)
    ranked = _rank_rows(
        [(row_partial, now), (row_complete, now)],
        priority_map={},
        min_quality_score=0.8,
    )
    assert ranked[0][0].source_name == "Agricharts"


def test_recency_wins_when_priority_and_completeness_tie() -> None:
    older = datetime.now(timezone.utc) - timedelta(hours=2)
    newer = datetime.now(timezone.utc)
    row_older = _build_row(source_name="GLG")
    row_newer = _build_row(source_name="Agricharts")
    ranked = _rank_rows(
        [(row_older, older), (row_newer, newer)],
        priority_map={},
        min_quality_score=0.8,
    )
    assert ranked[0][0].source_name == "Agricharts"


def test_source_name_tie_breaker_is_deterministic() -> None:
    now = datetime.now(timezone.utc)
    row_b = _build_row(source_name="Snobelen")
    row_a = _build_row(source_name="Agricharts")
    ranked = _rank_rows(
        [(row_b, now), (row_a, now)],
        priority_map={},
        min_quality_score=0.8,
    )
    assert ranked[0][0].source_name == "Agricharts"


def test_low_quality_aggregator_loses_to_company_source_by_global_policy() -> None:
    now = datetime.now(timezone.utc)
    # Agricharts candidate with low completeness (missing futures and cash/mt).
    aggregator_row = _build_row(
        source_name="Agricharts",
        futures_month=None,
        futures_price=None,
        cash_price_mt=None,
    )
    company_row = _build_row(source_name="GLG")
    ranked = _rank_rows(
        [(aggregator_row, now), (company_row, now)],
        priority_map={},
        min_quality_score=0.8,
    )
    assert ranked[0][0].source_name == "GLG"
