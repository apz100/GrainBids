from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.company import Company
from app.models.company_source_priority import CompanySourcePriority
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_key, canonical_source_name
from app.services.source_orchestration import list_sources_with_health, run_source_refresh, seed_sources_from_registry
from app.services.source_probe import SourceProbeEligibilityError, probe_source
from app.services.source_registry import get_adapter, list_pilot_adapter_keys
from app.services.us_source_candidates import seed_us_source_candidates


router = APIRouter(prefix="/api/sources", tags=["sources"])
FILE_AGGREGATOR_KEYS = {
    "ontario daily file",
    "ontario cash bids",
    "eastern ontario daily file",
    "eastern ontario cash bids",
}


@router.get("/module")
def module_info():
    return {
        "module": "sources",
        "primary_routes": [
            "/api/sources",
            "/api/sources/{id}/refresh",
            "/api/ingestion/sla",
        ],
    }


@router.get("")
def list_sources(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = list_sources_with_health(db, org_id=context.org_id)
    return {
        "rows": rows,
        "count": len(rows),
    }


@router.post("/seed")
def seed_sources(
    scope: str = Query("pilot", pattern="^(pilot|all)$"),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter_keys = list_pilot_adapter_keys() if scope == "pilot" else None
    created = seed_sources_from_registry(db, org_id=context.org_id, adapter_keys=adapter_keys)
    return {"created": created, "scope": scope, "adapter_keys": adapter_keys or "all"}


@router.post("/seed-us-candidates")
def seed_us_candidates(
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = seed_us_source_candidates(db, org_id=context.org_id)
    return {
        **result,
        "collection_status": "candidate",
        "is_active": False,
        "network_requests_started": 0,
    }


@router.post("/{source_id}/probe")
def probe_source_candidate(
    source_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.execute(
        select(Source).where(Source.id == source_id, Source.org_id == context.org_id)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    try:
        result = probe_source(source)
    except SourceProbeEligibilityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="source probe timed out") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="source probe fetch failed") from exc

    return {
        "source": {
            "id": str(source.id),
            "name": source.name,
            "adapter_key": source.adapter_key,
            "collection_status": source.collection_status,
            "is_active": source.is_active,
        },
        "result": result,
    }


@router.post("/{source_id}/promote-to-pilot")
def promote_source_to_pilot(
    source_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.execute(
        select(Source).where(Source.id == source_id, Source.org_id == context.org_id)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    if source.source_type != "automated" or not source.adapter_key:
        raise HTTPException(status_code=400, detail="only automated sources with a supported adapter can be piloted")
    try:
        adapter = get_adapter(source.adapter_key)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if adapter.requires_target and not (source.url or "").strip():
        raise HTTPException(status_code=400, detail="source URL is required before promotion")
    if source.collection_status == "quarantined":
        raise HTTPException(status_code=400, detail="quarantined sources must be reviewed before promotion")

    source.collection_status = "pilot"
    source.is_active = True
    source.next_poll_at = None
    db.commit()
    return {
        "id": str(source.id),
        "name": source.name,
        "collection_status": source.collection_status,
        "is_active": source.is_active,
    }


@router.post("/{source_id}/quarantine")
def quarantine_source(
    source_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.execute(
        select(Source).where(Source.id == source_id, Source.org_id == context.org_id)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    source.collection_status = "quarantined"
    source.is_active = False
    source.next_poll_at = None
    db.commit()
    return {
        "id": str(source.id),
        "name": source.name,
        "collection_status": source.collection_status,
        "is_active": source.is_active,
    }


@router.post("/{source_id}/refresh")
def refresh_source_by_id(
    source_id: uuid.UUID,
    commodity_id: uuid.UUID | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.execute(select(Source).where(Source.id == source_id, Source.org_id == context.org_id)).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    if not source.is_active:
        raise HTTPException(status_code=400, detail="source is inactive")
    if source.collection_status not in {"pilot", "active"}:
        raise HTTPException(status_code=400, detail="source must be in pilot or active collection status")

    resolved_commodity_id = commodity_id or _default_commodity_id(db)
    result = run_source_refresh(
        db,
        source=source,
        commodity_id=resolved_commodity_id,
        trigger_type="manual",
    )
    status = 200 if result.status == "completed" else 500
    payload = {
        "source_id": str(result.source_id),
        "source_name": result.source_name,
        "status": result.status,
        "attempts": result.attempts,
        "duration_ms": result.duration_ms,
        "row_count": result.row_count,
        "alerts_created": result.created_alert_count,
        "alerts_deduped": result.deduped_alert_count,
        "error_message": result.error_message,
    }
    if status >= 400:
        raise HTTPException(status_code=status, detail=payload)
    return {"result": payload}


@router.get("/priority")
def get_company_source_priority(
    company_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company = db.execute(
        select(Company).where(Company.id == company_id, Company.org_id == context.org_id)
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")

    rows = db.execute(
        select(CompanySourcePriority)
        .where(
            CompanySourcePriority.org_id == context.org_id,
            CompanySourcePriority.company_id == company_id,
            CompanySourcePriority.is_active.is_(True),
        )
        .order_by(CompanySourcePriority.priority_rank.asc(), CompanySourcePriority.source_key.asc())
    ).scalars().all()

    return {
        "company_id": str(company_id),
        "company_name": company.name,
        "rows": [
            {
                "id": str(row.id),
                "source_key": row.source_key,
                "priority_rank": int(row.priority_rank),
                "is_active": bool(row.is_active),
            }
            for row in rows
        ],
    }


@router.get("/priority/candidates")
def get_company_source_priority_candidates(
    company_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company = db.execute(
        select(Company).where(Company.id == company_id, Company.org_id == context.org_id)
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")

    query = (
        select(
            NormalizedPrice.source_name,
            func.count(NormalizedPrice.id).label("row_count"),
            func.sum(case((NormalizedPrice.is_canonical.is_(True), 1), else_=0)).label("canonical_count"),
        )
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(
            Source.org_id == context.org_id,
            NormalizedPrice.company_id == company_id,
            NormalizedPrice.source_name.is_not(None),
        )
        .group_by(NormalizedPrice.source_name)
    )

    merged: dict[str, dict[str, object]] = {}
    for source_name, row_count, canonical_count in db.execute(query).all():
        display_name = canonical_source_name(source_name) or (source_name or "").strip()
        source_key = canonical_key(display_name)
        if not source_key:
            continue
        row_value = int(row_count or 0)
        canonical_value = int(canonical_count or 0)
        current = merged.get(source_key)
        if current is None:
            merged[source_key] = {
                "source_key": source_key,
                "display_name": display_name,
                "row_count": row_value,
                "canonical_count": canonical_value,
            }
        else:
            current["row_count"] = int(current["row_count"]) + row_value
            current["canonical_count"] = int(current["canonical_count"]) + canonical_value

    candidates = list(merged.values())

    def _policy_rank(source_key: str) -> int:
        if source_key == company.canonical_key:
            return 0
        if source_key in settings.canonical_aggregator_sources_set or source_key in FILE_AGGREGATOR_KEYS:
            return 2
        return 1

    candidates.sort(
        key=lambda row: (
            _policy_rank(str(row["source_key"])),
            -int(row["row_count"]),
            str(row["source_key"]),
        )
    )

    for row in candidates:
        row_count = int(row["row_count"])
        canonical_count = int(row["canonical_count"])
        row["winner_rate"] = float(canonical_count / row_count) if row_count else 0.0
        row["policy_rank"] = _policy_rank(str(row["source_key"]))

    return {
        "company_id": str(company_id),
        "company_name": company.name,
        "company_key": company.canonical_key,
        "rows": candidates,
    }


@router.put("/priority")
def put_company_source_priority(
    company_id: uuid.UUID = Query(...),
    source_keys: str = Query(..., description="Ordered comma-separated source keys"),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company = db.execute(
        select(Company).where(Company.id == company_id, Company.org_id == context.org_id)
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")

    ordered_keys: list[str] = []
    seen: set[str] = set()
    for raw in source_keys.split(","):
        normalized = canonical_key(canonical_source_name(raw))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered_keys.append(normalized)
    if not ordered_keys:
        raise HTTPException(status_code=400, detail="source_keys cannot be empty")

    existing = db.execute(
        select(CompanySourcePriority).where(
            CompanySourcePriority.org_id == context.org_id,
            CompanySourcePriority.company_id == company_id,
        )
    ).scalars().all()
    existing_by_key = {canonical_key(row.source_key) or row.source_key: row for row in existing}

    for rank, source_key in enumerate(ordered_keys, start=1):
        row = existing_by_key.get(source_key)
        if row is None:
            db.add(
                CompanySourcePriority(
                    org_id=context.org_id,
                    company_id=company_id,
                    source_key=source_key,
                    priority_rank=rank,
                    is_active=True,
                )
            )
        else:
            row.priority_rank = rank
            row.is_active = True
            row.source_key = source_key

    for row in existing:
        row_key = canonical_key(row.source_key) or row.source_key
        if row_key not in seen:
            row.is_active = False

    db.commit()
    return {
        "company_id": str(company_id),
        "company_name": company.name,
        "source_keys": ordered_keys,
    }


@router.post("/priority/seed-defaults")
def seed_company_source_priority_defaults(
    overwrite_existing: bool = Query(False),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    aggregator_keys = settings.canonical_aggregator_sources_set | FILE_AGGREGATOR_KEYS
    companies = db.execute(select(Company).where(Company.org_id == context.org_id)).scalars().all()
    seeded_companies = 0
    touched_rows = 0
    skipped_single_source = 0
    skipped_existing = 0

    for company in companies:
        source_rows = db.execute(
            select(func.distinct(NormalizedPrice.source_name))
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .where(
                Source.org_id == context.org_id,
                NormalizedPrice.company_id == company.id,
            )
        ).scalars().all()

        ranked_keys: list[str] = []
        for source_name in source_rows:
            key = canonical_key(canonical_source_name(source_name))
            if key:
                ranked_keys.append(key)
        ranked_keys = list(dict.fromkeys(ranked_keys))
        if not ranked_keys:
            continue
        if len(ranked_keys) < 2:
            skipped_single_source += 1
            continue

        def priority_for_source(source_key: str) -> tuple[int, str]:
            if source_key == company.canonical_key:
                return (1, source_key)
            if source_key in aggregator_keys:
                return (90, source_key)
            return (20, source_key)

        ordered_keys = [item for item, _ in sorted(((key, priority_for_source(key)) for key in ranked_keys), key=lambda it: it[1])]

        existing = db.execute(
            select(CompanySourcePriority).where(
                CompanySourcePriority.org_id == context.org_id,
                CompanySourcePriority.company_id == company.id,
            )
        ).scalars().all()
        if not overwrite_existing and any(row.is_active for row in existing):
            skipped_existing += 1
            continue
        existing_by_key = {canonical_key(row.source_key) or row.source_key: row for row in existing}
        seen: set[str] = set()
        for rank, source_key in enumerate(ordered_keys, start=1):
            seen.add(source_key)
            row = existing_by_key.get(source_key)
            if row is None:
                db.add(
                    CompanySourcePriority(
                        org_id=context.org_id,
                        company_id=company.id,
                        source_key=source_key,
                        priority_rank=rank,
                        is_active=True,
                    )
                )
                touched_rows += 1
            else:
                row.priority_rank = rank
                row.is_active = True
                row.source_key = source_key
                touched_rows += 1
        for row in existing:
            row_key = canonical_key(row.source_key) or row.source_key
            if row_key not in seen:
                row.is_active = False
        seeded_companies += 1

    db.commit()
    return {
        "seeded_companies": seeded_companies,
        "touched_rows": touched_rows,
        "skipped_single_source": skipped_single_source,
        "skipped_existing": skipped_existing,
        "overwrite_existing": overwrite_existing,
    }


@router.get("/canonical-coverage")
def canonical_coverage(
    days: int = Query(7, ge=1, le=90),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = (
        select(
            NormalizedPrice.source_name,
            func.count(NormalizedPrice.id).label("row_count"),
            func.sum(case((NormalizedPrice.is_canonical.is_(True), 1), else_=0)).label("canonical_count"),
        )
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(
            Source.org_id == context.org_id,
            PriceSnapshot.captured_at >= cutoff,
            NormalizedPrice.source_name.is_not(None),
        )
        .group_by(NormalizedPrice.source_name)
        .order_by(desc("canonical_count"), desc("row_count"))
    )
    rows = []
    for source_name, row_count, canonical_count in db.execute(query).all():
        canonical_value = int(canonical_count or 0)
        row_value = int(row_count or 0)
        rate = float(canonical_value / row_value) if row_value else 0.0
        rows.append(
            {
                "source_name": canonical_source_name(source_name),
                "source_key": canonical_key(canonical_source_name(source_name)),
                "row_count": row_value,
                "canonical_count": canonical_value,
                "winner_rate": rate,
            }
        )
    return {"rows": rows, "days": days}


def _default_commodity_id(db: Session) -> uuid.UUID:
    commodity = db.execute(select(Commodity).order_by(Commodity.created_at.asc()).limit(1)).scalar_one_or_none()
    if commodity is None:
        raise HTTPException(status_code=400, detail="No commodity exists. Create one first.")
    return commodity.id
