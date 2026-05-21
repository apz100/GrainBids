from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import uuid

from sqlalchemy import String, cast, desc, func, select, tuple_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.ingestion_run import IngestionRun
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.canonical_resolver import _market_key_from_row, resolve_canonical_rows_for_snapshot
from app.services.market_canonicalization import (
    canonical_commodity_name,
    canonical_key,
    canonical_location_name,
    canonical_source_name,
    normalize_text,
)
from app.services.source_file_ingestion import list_ingestion_runs


def recompute_latest_snapshot_canonical_rows(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
) -> dict[str, object]:
    latest_snapshot = _get_latest_snapshot(db, org_id=org_id, source_id=source_id)
    if latest_snapshot is None:
        raise ValueError("No snapshot found for this organization")

    snapshot, source = latest_snapshot
    result = resolve_canonical_rows_for_snapshot(
        db,
        org_id=org_id,
        snapshot_id=snapshot.id,
    )
    db.commit()
    return {
        "snapshot_id": str(snapshot.id),
        "source_id": str(source.id),
        "source_name": source.name,
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        **result,
    }


def build_ingestion_diagnostics(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    duplicate_limit: int = 10,
) -> dict[str, object]:
    latest_run = _get_latest_run(db, org_id=org_id, source_id=source_id)
    latest_snapshot = _get_latest_snapshot(db, org_id=org_id, source_id=source_id)
    if latest_snapshot is None:
        return {
            "latest_run": _serialize_run(latest_run),
            "latest_snapshot": None,
            "duplicate_candidates_by_company": [],
        }

    snapshot, source = latest_snapshot
    snapshot_rows = _load_snapshot_rows(db, org_id=org_id, snapshot_id=snapshot.id)
    impacted_keys = {_market_key_from_row(row) for row in snapshot_rows}
    candidate_rows = _load_candidate_rows_for_market_keys(db, org_id=org_id, market_keys=impacted_keys)
    company_names = _load_company_names(db, rows=candidate_rows)
    duplicate_candidates = summarize_duplicate_candidates(candidate_rows, company_names=company_names)[:duplicate_limit]

    canonical_row_count = sum(1 for row in snapshot_rows if bool(row.is_canonical))
    duplicate_market_key_count = sum(1 for group in _group_rows_by_market_key(candidate_rows).values() if len(group) > 1)
    company_count = len(
        {
            str(row.company_id) if row.company_id else (canonical_key(canonical_source_name(row.source_name)) or "-")
            for row in snapshot_rows
        }
    )

    return {
        "latest_run": _serialize_run(latest_run),
        "latest_snapshot": {
            "id": str(snapshot.id),
            "source_id": str(source.id),
            "source_name": source.name,
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
            "source_file_path": _raw_payload_string(snapshot.raw_payload_json, "source_file_path") or (source.url or None),
            "ingestion_run_id": _raw_payload_string(snapshot.raw_payload_json, "ingestion_run_id"),
            "commodity_id": _raw_payload_string(snapshot.raw_payload_json, "commodity_id"),
            "commodity_name": _raw_payload_string(snapshot.raw_payload_json, "commodity_name"),
            "row_count": len(snapshot_rows),
            "canonical_row_count": canonical_row_count,
            "non_canonical_row_count": len(snapshot_rows) - canonical_row_count,
            "impacted_market_key_count": len(impacted_keys),
            "duplicate_market_key_count": duplicate_market_key_count,
            "company_count": company_count,
        },
        "duplicate_candidates_by_company": duplicate_candidates,
    }


def summarize_duplicate_candidates(
    rows: list[NormalizedPrice],
    *,
    company_names: dict[uuid.UUID, str] | None = None,
) -> list[dict[str, object]]:
    grouped = _group_rows_by_market_key(rows)
    aggregated: dict[str, dict[str, object]] = {}
    for market_rows in grouped.values():
        if len(market_rows) < 2:
            continue
        first = market_rows[0]
        company_name = _company_display_name(first, company_names=company_names or {})
        company_key = str(first.company_id) if first.company_id else (canonical_key(company_name) or company_name)
        record = aggregated.get(company_key)
        if record is None:
            record = {
                "company_id": str(first.company_id) if first.company_id else None,
                "company_name": company_name,
                "duplicate_market_keys": 0,
                "candidate_rows": 0,
                "alternate_rows": 0,
                "canonical_rows": 0,
                "sample_markets": [],
            }
            aggregated[company_key] = record

        record["duplicate_market_keys"] = int(record["duplicate_market_keys"]) + 1
        record["candidate_rows"] = int(record["candidate_rows"]) + len(market_rows)
        record["alternate_rows"] = int(record["alternate_rows"]) + max(0, len(market_rows) - 1)
        record["canonical_rows"] = int(record["canonical_rows"]) + sum(1 for row in market_rows if bool(row.is_canonical))

        sample_markets = list(record["sample_markets"])
        market_label = _market_label(first)
        if market_label and market_label not in sample_markets and len(sample_markets) < 3:
            sample_markets.append(market_label)
        record["sample_markets"] = sample_markets

    return sorted(
        aggregated.values(),
        key=lambda row: (
            -int(row["duplicate_market_keys"]),
            -int(row["candidate_rows"]),
            str(row["company_name"]).casefold(),
        ),
    )


def _get_latest_run(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None,
) -> IngestionRun | None:
    runs = list_ingestion_runs(db, limit=50, org_id=org_id)
    if source_id is None:
        return runs[0] if runs else None
    source = db.execute(select(Source).where(Source.id == source_id, Source.org_id == org_id)).scalar_one_or_none()
    if source is None:
        return None
    for run in runs:
        if run.source_name == source.name:
            return run
    return None


def _serialize_run(run: IngestionRun | None) -> dict[str, object] | None:
    if run is None:
        return None
    return {
        "id": str(run.id),
        "source_name": run.source_name,
        "source_identifier": run.source_identifier,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "status": run.status,
        "trigger_type": run.trigger_type,
        "raw_row_count": run.raw_row_count,
        "normalized_row_count": run.normalized_row_count,
        "duplicate_key_count": run.duplicate_key_count,
        "rejected_row_count": run.rejected_row_count,
        "missing_required_count": run.missing_required_count,
        "parse_success_rate": float(run.parse_success_rate) if run.parse_success_rate is not None else None,
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
    }


def _get_latest_snapshot(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None,
) -> tuple[PriceSnapshot, Source] | None:
    query = select(PriceSnapshot, Source).join(Source, Source.id == PriceSnapshot.source_id).where(Source.org_id == org_id)
    if source_id is not None:
        query = query.where(Source.id == source_id)
    query = query.order_by(desc(PriceSnapshot.captured_at), desc(PriceSnapshot.id)).limit(1)
    return db.execute(query).one_or_none()


def _load_snapshot_rows(
    db: Session,
    *,
    org_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> list[NormalizedPrice]:
    return (
        db.execute(
            select(NormalizedPrice)
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .where(
                Source.org_id == org_id,
                NormalizedPrice.snapshot_id == snapshot_id,
            )
        )
        .scalars()
        .all()
    )


def _load_candidate_rows_for_market_keys(
    db: Session,
    *,
    org_id: uuid.UUID,
    market_keys: set[tuple[str, str, str, str, str]],
) -> list[NormalizedPrice]:
    if not market_keys:
        return []

    company_expr = func.coalesce(cast(NormalizedPrice.company_id, String), func.lower(func.trim(NormalizedPrice.source_name)))
    location_expr = func.coalesce(cast(NormalizedPrice.location_id, String), func.lower(func.trim(NormalizedPrice.location)))
    commodity_expr = func.lower(func.trim(NormalizedPrice.commodity_name))
    delivery_expr = func.lower(
        func.trim(func.coalesce(NormalizedPrice.delivery_end, NormalizedPrice.delivery_label, NormalizedPrice.delivery_start, ""))
    )
    futures_expr = func.lower(func.trim(func.coalesce(NormalizedPrice.futures_month, "")))
    market_key_expr = tuple_(company_expr, location_expr, commodity_expr, delivery_expr, futures_expr)

    return (
        db.execute(
            select(NormalizedPrice)
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .where(
                Source.org_id == org_id,
                Source.is_active.is_(True),
                market_key_expr.in_(list(market_keys)),
            )
        )
        .scalars()
        .all()
    )


def _load_company_names(
    db: Session,
    *,
    rows: list[NormalizedPrice],
) -> dict[uuid.UUID, str]:
    company_ids = {row.company_id for row in rows if row.company_id is not None}
    if not company_ids:
        return {}
    return {
        company.id: company.name
        for company in db.execute(select(Company).where(Company.id.in_(company_ids))).scalars().all()
    }


def _group_rows_by_market_key(
    rows: list[NormalizedPrice],
) -> dict[tuple[str, str, str, str, str], list[NormalizedPrice]]:
    grouped: dict[tuple[str, str, str, str, str], list[NormalizedPrice]] = defaultdict(list)
    for row in rows:
        grouped[_market_key_from_row(row)].append(row)
    return grouped


def _company_display_name(
    row: NormalizedPrice,
    *,
    company_names: dict[uuid.UUID, str],
) -> str:
    if row.company_id and row.company_id in company_names:
        return company_names[row.company_id]
    return canonical_source_name(row.source_name) or (row.source_name or "").strip() or "Unknown"


def _market_label(row: NormalizedPrice) -> str:
    location = canonical_location_name(row.location) or "-"
    commodity = canonical_commodity_name(row.commodity_name) or "-"
    delivery = normalize_text(row.delivery_label or row.delivery_end or row.delivery_start) or "-"
    futures = normalize_text(row.futures_month) or "-"
    return f"{location} | {commodity} | {delivery} | {futures}"


def _raw_payload_string(payload: dict | None, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return str(value) if value is not None else None
