from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable
import uuid

from sqlalchemy import String, cast, func, select, tuple_, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company_source_priority import CompanySourcePriority
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import (
    canonical_commodity_name,
    canonical_key,
    canonical_location_name,
    canonical_source_name,
    normalize_text,
)


MarketKey = tuple[str, str, str, str, str]


def resolve_canonical_rows_for_snapshot(
    db: Session,
    *,
    org_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> dict[str, int]:
    snapshot_rows = db.execute(
        select(NormalizedPrice)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id, NormalizedPrice.snapshot_id == snapshot_id)
    ).scalars().all()
    if not snapshot_rows:
        return {"impacted_keys": 0, "updated_rows": 0, "canonical_rows": 0}

    # Fast path: the ingestion job only needs the latest snapshot rows to be visible.
    # Historical canonical backfills use resolve_canonical_rows_for_market_keys() directly.
    db.execute(
        update(NormalizedPrice)
        .where(NormalizedPrice.snapshot_id == snapshot_id)
        .values(
            is_canonical=True,
            canonical_rank=1,
            canonical_reason="snapshot_latest",
        )
    )
    db.flush()

    impacted_keys = {_market_key_from_row(row) for row in snapshot_rows}
    return {
        "impacted_keys": len(impacted_keys),
        "updated_rows": len(snapshot_rows),
        "canonical_rows": len(snapshot_rows),
    }


def resolve_canonical_rows_for_market_keys(
    db: Session,
    *,
    org_id: uuid.UUID,
    market_keys: Iterable[MarketKey],
    allow_inactive_sources: bool = False,
) -> dict[str, int]:
    deduped_keys = list(dict.fromkeys(market_keys))
    if not deduped_keys:
        return {"impacted_keys": 0, "updated_rows": 0, "canonical_rows": 0}

    company_expr = func.coalesce(cast(NormalizedPrice.company_id, String), func.lower(func.trim(NormalizedPrice.source_name)))
    location_expr = func.coalesce(cast(NormalizedPrice.location_id, String), func.lower(func.trim(NormalizedPrice.location)))
    commodity_expr = func.lower(func.trim(NormalizedPrice.commodity_name))
    delivery_expr = func.lower(
        func.trim(func.coalesce(NormalizedPrice.delivery_end, NormalizedPrice.delivery_label, NormalizedPrice.delivery_start, ""))
    )
    futures_expr = func.lower(func.trim(func.coalesce(NormalizedPrice.futures_month, "")))
    market_key_expr = tuple_(company_expr, location_expr, commodity_expr, delivery_expr, futures_expr)

    query = (
        select(NormalizedPrice, PriceSnapshot.captured_at, Source.is_active)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id)
        .where(market_key_expr.in_(deduped_keys))
    )
    if not allow_inactive_sources:
        query = query.where(Source.is_active.is_(True))

    candidates = db.execute(query).all()
    if not candidates:
        return {"impacted_keys": len(deduped_keys), "updated_rows": 0, "canonical_rows": 0}

    grouped: dict[MarketKey, list[tuple[NormalizedPrice, datetime | None]]] = defaultdict(list)
    for row, captured_at, _is_active in candidates:
        grouped[_market_key_from_row(row)].append((row, captured_at))

    company_ids = {row.company_id for row, _captured, _is_active in candidates if row.company_id is not None}
    priority_map = _load_priority_map(db, org_id=org_id, company_ids=company_ids)

    min_quality_score = settings.canonical_min_quality_score
    updated_rows = 0
    canonical_rows = 0
    for key, rows in grouped.items():
        ranked = _rank_rows(rows, priority_map=priority_map, min_quality_score=min_quality_score)
        if not ranked:
            continue
        winner = ranked[0][0]
        reason = _winner_reason(ranked)
        for index, (row, _score_meta) in enumerate(ranked, start=1):
            row.is_canonical = row.id == winner.id
            row.canonical_rank = index
            row.canonical_reason = reason if row.id == winner.id else f"alternate:{reason}"
            updated_rows += 1
            if row.id == winner.id:
                canonical_rows += 1
    db.flush()
    return {"impacted_keys": len(grouped), "updated_rows": updated_rows, "canonical_rows": canonical_rows}


def _load_priority_map(
    db: Session,
    *,
    org_id: uuid.UUID,
    company_ids: set[uuid.UUID],
) -> dict[tuple[uuid.UUID, str], int]:
    if not company_ids:
        return {}
    rows = db.execute(
        select(
            CompanySourcePriority.company_id,
            CompanySourcePriority.source_key,
            CompanySourcePriority.priority_rank,
        ).where(
            CompanySourcePriority.org_id == org_id,
            CompanySourcePriority.company_id.in_(company_ids),
            CompanySourcePriority.is_active.is_(True),
        )
    ).all()
    output: dict[tuple[uuid.UUID, str], int] = {}
    for company_id, source_key, priority_rank in rows:
        key = canonical_key(source_key)
        if company_id is None or key is None:
            continue
        output[(company_id, key)] = int(priority_rank)
    return output


def _market_key_from_row(row: NormalizedPrice) -> MarketKey:
    source_key = canonical_key(canonical_source_name(row.source_name)) or "-"
    company_key = str(row.company_id) if row.company_id else source_key
    location_fallback = canonical_key(canonical_location_name(row.location)) or "-"
    location_key = str(row.location_id) if row.location_id else location_fallback
    commodity_key = canonical_key(canonical_commodity_name(row.commodity_name)) or "-"
    delivery_text = normalize_text(row.delivery_end or row.delivery_label or row.delivery_start)
    delivery_key = canonical_key(delivery_text) or "-"
    futures_key = canonical_key(row.futures_month) or "-"
    return (company_key, location_key, commodity_key, delivery_key, futures_key)


def _row_quality_score(row: NormalizedPrice) -> float:
    checks = [
        normalize_text(row.futures_month) is not None,
        row.futures_price is not None,
        row.basis is not None,
        row.cash_price_bu is not None,
        row.cash_price_mt is not None,
        normalize_text(row.delivery_end or row.delivery_label or row.delivery_start) is not None,
    ]
    valid_count = sum(1 for item in checks if item)
    return valid_count / float(len(checks))


def _is_valid_commodity(row: NormalizedPrice) -> bool:
    label = canonical_key(canonical_commodity_name(row.commodity_name))
    if label is None:
        return False
    return label not in settings.invalid_commodity_labels_set


def _rank_rows(
    rows: list[tuple[NormalizedPrice, datetime | None]],
    *,
    priority_map: dict[tuple[uuid.UUID, str], int],
    min_quality_score: float,
) -> list[tuple[NormalizedPrice, dict[str, object]]]:
    aggregator_sources = settings.canonical_aggregator_sources_set
    aggregator_gap = max(0.0, float(settings.canonical_aggregator_gap_threshold))
    scored: list[tuple[NormalizedPrice, dict[str, object]]] = []
    for row, captured_at in rows:
        source_key = canonical_key(canonical_source_name(row.source_name)) or "-"
        priority_rank = None
        if row.company_id is not None:
            priority_rank = priority_map.get((row.company_id, source_key))
        quality_score = _row_quality_score(row)
        is_aggregator = source_key.casefold() in aggregator_sources
        commodity_valid = _is_valid_commodity(row)
        quality_pass = commodity_valid and quality_score >= min_quality_score
        captured_ts = _captured_at_epoch(captured_at)
        scored.append(
            (
                row,
                {
                    "source_key": source_key,
                    "priority_rank": priority_rank,
                    "quality_score": quality_score,
                    "quality_pass": quality_pass,
                    "is_aggregator": is_aggregator,
                    "captured_ts": captured_ts,
                },
            )
        )

    any_quality_pass = any(meta["quality_pass"] for _, meta in scored)
    non_aggregator_scores = [float(meta["quality_score"]) for _, meta in scored if not bool(meta["is_aggregator"])]
    best_non_aggregator_score = max(non_aggregator_scores) if non_aggregator_scores else None

    for _, meta in scored:
        deprioritize = False
        if (
            bool(meta["is_aggregator"])
            and best_non_aggregator_score is not None
            and (best_non_aggregator_score - float(meta["quality_score"])) >= aggregator_gap
        ):
            deprioritize = True
        meta["deprioritize_aggregator"] = deprioritize

    def sort_key(item: tuple[NormalizedPrice, dict[str, object]]) -> tuple[float, int, float, float, str]:
        row, meta = item
        rank = meta["priority_rank"]
        priority_value = float(rank) if rank is not None else 100000.0
        aggregator_penalty = 1 if bool(meta["deprioritize_aggregator"]) else 0
        quality_bucket = 0 if bool(meta["quality_pass"]) else 1 if any_quality_pass else 0
        quality_score = float(meta["quality_score"])
        captured_ts = float(meta["captured_ts"])
        source_name = canonical_source_name(row.source_name) or ""
        return (
            priority_value,
            aggregator_penalty,
            quality_bucket,
            -quality_score,
            -captured_ts,
            source_name.casefold(),
        )

    scored.sort(key=sort_key)
    return scored


def _captured_at_epoch(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _winner_reason(ranked: list[tuple[NormalizedPrice, dict[str, object]]]) -> str:
    winner_row, winner_meta = ranked[0]
    if winner_meta["priority_rank"] is not None:
        return f"priority:{winner_meta['source_key']}"
    if bool(winner_meta.get("deprioritize_aggregator")) is False:
        if any(bool(meta.get("deprioritize_aggregator")) for _, meta in ranked[1:]):
            return "source_preference_non_aggregator"
    if len(ranked) == 1:
        return "single_candidate"
    second_meta = ranked[1][1]
    winner_quality = float(winner_meta["quality_score"])
    second_quality = float(second_meta["quality_score"])
    if winner_quality > second_quality:
        return "completeness"
    winner_captured = float(winner_meta["captured_ts"])
    second_captured = float(second_meta["captured_ts"])
    if winner_captured > second_captured:
        return "recency"
    winner_source = canonical_source_name(winner_row.source_name) or "-"
    return f"tie_breaker:{winner_source}"
