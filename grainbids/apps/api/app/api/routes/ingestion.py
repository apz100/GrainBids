from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.ingestion_diagnostics import build_ingestion_diagnostics
from app.services.market_canonicalization import canonical_key, canonical_location_name, location_kind_for_name
from app.services.source_company_identity_diagnostics import list_ambiguous_location_company_candidates
from app.services.source_orchestration import build_sla_summary
from app.services.source_file_ingestion import (
    ingest_source_file,
    list_ingestion_runs,
    reprocess_latest_file_source,
    run_scheduled_file_ingestion_cycle,
)
from app.services.upload_csv import summarize_quality


router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.get("/runs")
def get_ingestion_runs(
    limit: int = Query(25, ge=1, le=200),
    _context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = []
    for row in list_ingestion_runs(db, limit=limit, org_id=_context.org_id):
        rows.append(
            {
                "id": str(row.id),
                "source_name": row.source_name,
                "source_identifier": row.source_identifier,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "status": row.status,
                "trigger_type": row.trigger_type,
                "attempt_number": row.attempt_number,
                "max_attempts": row.max_attempts,
                "raw_row_count": row.raw_row_count,
                "normalized_row_count": row.normalized_row_count,
                "created_alert_count": row.created_alert_count,
                "deduped_alert_count": row.deduped_alert_count,
                "duplicate_key_count": row.duplicate_key_count,
                "rejected_row_count": row.rejected_row_count,
                "missing_required_count": row.missing_required_count,
                "row_reject_reasons": row.row_reject_reasons_json,
                "duration_ms": row.duration_ms,
                "parse_success_rate": float(row.parse_success_rate) if row.parse_success_rate is not None else None,
                "schema_drift_count": row.schema_drift_count,
                "error_message": row.error_message,
                "quality_summary": summarize_quality(
                    raw_row_count=row.raw_row_count,
                    normalized_row_count=row.normalized_row_count,
                    duplicate_key_count=row.duplicate_key_count,
                    rejected_row_count=row.rejected_row_count,
                    missing_required_count=row.missing_required_count,
                    parse_success_rate=float(row.parse_success_rate) if row.parse_success_rate is not None else None,
                    row_reject_reasons=row.row_reject_reasons_json or {},
                ),
            }
        )
    return {"rows": rows}


@router.get("/sla")
def get_ingestion_sla(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    summary = build_sla_summary(db, org_id=context.org_id)
    recent_runs = list_ingestion_runs(db, limit=5, org_id=context.org_id)
    if recent_runs:
        summary["latest_quality"] = summarize_quality(
            raw_row_count=recent_runs[0].raw_row_count,
            normalized_row_count=recent_runs[0].normalized_row_count,
            duplicate_key_count=recent_runs[0].duplicate_key_count,
            rejected_row_count=recent_runs[0].rejected_row_count,
            missing_required_count=recent_runs[0].missing_required_count,
            parse_success_rate=float(recent_runs[0].parse_success_rate) if recent_runs[0].parse_success_rate is not None else None,
            row_reject_reasons=recent_runs[0].row_reject_reasons_json or {},
        )
    return summary


@router.get("/diagnostics")
def get_ingestion_diagnostics(
    source_id: uuid.UUID | None = Query(None),
    duplicate_limit: int = Query(10, ge=1, le=50),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if source_id is not None:
        _assert_source_org_scope(db, source_id=source_id, org_id=context.org_id)
    return build_ingestion_diagnostics(
        db,
        org_id=context.org_id,
        source_id=source_id,
        duplicate_limit=duplicate_limit,
    )


@router.get("/company-identity/ambiguous-locations")
def get_ambiguous_location_company_candidates(
    source_id: uuid.UUID | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if source_id is not None:
        _assert_source_org_scope(db, source_id=source_id, org_id=context.org_id)
    return list_ambiguous_location_company_candidates(
        db,
        org_id=context.org_id,
        source_id=source_id,
        limit=limit,
    )


@router.get("/company-resolution/coverage")
def get_company_resolution_coverage(
    target: int = Query(65, ge=1, le=1000),
    include_top_unmapped: bool = Query(True),
    top_limit: int = Query(25, ge=1, le=200),
    location_kind: Literal["elevator", "benchmark", "all"] = Query("elevator"),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    active_rows = _list_active_location_resolution_rows(db, org_id=context.org_id)
    return _build_company_resolution_coverage_payload(
        active_rows=active_rows,
        target=target,
        include_top_unmapped=include_top_unmapped,
        top_limit=top_limit,
        location_kind=location_kind,
    )


@router.post("/source-file/run")
def run_source_file_ingestion(
    source_file_path: str | None = Query(None),
    source_name: str | None = Query(None),
    source_id: uuid.UUID | None = Query(None),
    commodity_id: uuid.UUID | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    file_path = source_file_path or settings.daily_source_file_path
    name = source_name or settings.daily_source_name
    resolved_source_id = source_id or _parse_uuid(settings.daily_source_id, "DAILY_SOURCE_ID")
    resolved_commodity_id = commodity_id or _parse_optional_uuid(settings.daily_commodity_id, "DAILY_COMMODITY_ID")
    _assert_source_org_scope(db, source_id=resolved_source_id, org_id=context.org_id)

    if not file_path:
        raise HTTPException(status_code=400, detail="source_file_path is required")

    result = ingest_source_file(
        db,
        source_file_path=file_path,
        source_name=name,
        source_id=resolved_source_id,
        commodity_id=resolved_commodity_id,
        trigger_type="manual",
        attempt_number=1,
        max_attempts=1,
    )

    payload = _serialize_result(result)
    payload["quality_summary"] = summarize_quality(
        raw_row_count=result.raw_row_count,
        normalized_row_count=result.normalized_row_count,
        duplicate_key_count=result.duplicate_key_count,
        rejected_row_count=result.rejected_row_count,
        missing_required_count=result.missing_required_count,
        parse_success_rate=result.parse_success_rate,
        row_reject_reasons=result.row_reject_reasons or {},
    )
    status_code = 500 if result.status == "failed" else 200
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=payload)
    return {"result": payload}


@router.post("/source-file/reprocess-latest")
def reprocess_latest_source_file_ingestion(
    source_id: uuid.UUID | None = Query(None),
    source_file_path: str | None = Query(None),
    duplicate_limit: int = Query(10, ge=1, le=50),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if source_id is not None:
        _assert_source_org_scope(db, source_id=source_id, org_id=context.org_id)

    try:
        target, result = reprocess_latest_file_source(
            db,
            org_id=context.org_id,
            source_id=source_id,
            source_file_path_override=source_file_path or settings.reprocess_source_file_path_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = _serialize_result(result)
    payload["reprocess_target"] = {
        "source_id": str(target.source_id),
        "source_name": target.source_name,
        "commodity_id": str(target.commodity_id),
        "snapshot_id": str(target.snapshot_id),
        "captured_at": target.captured_at.isoformat() if target.captured_at else None,
        "source_file_path": target.source_file_path,
    }
    payload["quality_summary"] = summarize_quality(
        raw_row_count=result.raw_row_count,
        normalized_row_count=result.normalized_row_count,
        duplicate_key_count=result.duplicate_key_count,
        rejected_row_count=result.rejected_row_count,
        missing_required_count=result.missing_required_count,
        parse_success_rate=result.parse_success_rate,
        row_reject_reasons=result.row_reject_reasons or {},
    )
    payload["diagnostics"] = build_ingestion_diagnostics(
        db,
        org_id=context.org_id,
        source_id=target.source_id,
        duplicate_limit=duplicate_limit,
    )
    status_code = 500 if result.status == "failed" else 200
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=payload)
    return {"result": payload}


@router.post("/source-files/run")
def run_scheduled_source_file_cycle(
    commodity_id: uuid.UUID | None = Query(None),
    max_attempts: int | None = Query(None, ge=1, le=10),
    source_ids: list[uuid.UUID] | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_commodity_id = commodity_id or _default_commodity_id(db)
    _assert_commodity_exists(db, commodity_id=resolved_commodity_id)
    if source_ids:
        for source_id in source_ids:
            _assert_source_org_scope(db, source_id=source_id, org_id=context.org_id)

    results = run_scheduled_file_ingestion_cycle(
        db,
        commodity_id=resolved_commodity_id,
        org_id=context.org_id,
        max_attempts=max_attempts,
        source_ids=source_ids,
    )
    failed = [result for result in results if result.status != "completed"]
    return {
        "summary": {
            "total_sources": len(results),
            "completed_sources": len(results) - len(failed),
            "failed_sources": len(failed),
        },
        "results": [_serialize_result(result) for result in results],
    }


def _assert_source_org_scope(db: Session, *, source_id: uuid.UUID, org_id: uuid.UUID) -> None:
    source = db.execute(select(Source.id).where(Source.id == source_id, Source.org_id == org_id)).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found for this organization")


def _parse_uuid(value: str, setting_name: str) -> uuid.UUID:
    if not value:
        raise HTTPException(status_code=400, detail=f"{setting_name} is required")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{setting_name} must be a valid UUID") from exc


def _parse_optional_uuid(value: str, setting_name: str) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{setting_name} must be a valid UUID") from exc


def _default_commodity_id(db: Session) -> uuid.UUID:
    commodity = db.execute(select(Commodity).order_by(Commodity.created_at.asc()).limit(1)).scalar_one_or_none()
    if commodity is None:
        raise HTTPException(status_code=400, detail="No commodity exists. Create one first.")
    return commodity.id


def _assert_commodity_exists(db: Session, *, commodity_id: uuid.UUID) -> None:
    commodity = db.execute(select(Commodity.id).where(Commodity.id == commodity_id)).scalar_one_or_none()
    if commodity is None:
        raise HTTPException(status_code=404, detail="commodity not found")


def _serialize_result(result):
    payload = asdict(result)
    for key, value in list(payload.items()):
        if isinstance(value, uuid.UUID):
            payload[key] = str(value)
    return payload


def _list_active_location_resolution_rows(
    db: Session,
    *,
    org_id: uuid.UUID,
) -> list[dict[str, object]]:
    latest_snapshot_per_source = (
        select(
            PriceSnapshot.source_id.label("source_id"),
            func.max(PriceSnapshot.captured_at).label("latest_captured_at"),
        )
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(
            Source.org_id == org_id,
            Source.is_active.is_(True),
        )
        .group_by(PriceSnapshot.source_id)
        .subquery()
    )

    query = (
        select(
            Location.id,
            Location.name,
            Location.company_id,
            NormalizedPrice.location,
            PriceSnapshot.captured_at,
        )
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .join(
            latest_snapshot_per_source,
            and_(
                latest_snapshot_per_source.c.source_id == PriceSnapshot.source_id,
                latest_snapshot_per_source.c.latest_captured_at == PriceSnapshot.captured_at,
            ),
        )
        .outerjoin(
            Location,
            and_(
                Location.id == NormalizedPrice.location_id,
                Location.org_id == org_id,
            ),
        )
        .where(
            Source.org_id == org_id,
            Source.is_active.is_(True),
        )
    )

    rows: list[dict[str, object]] = []
    for location_id, location_name, company_id, raw_location, captured_at in db.execute(query).all():
        rows.append(
            {
                "location_id": location_id,
                "location_name": location_name,
                "company_id": company_id,
                "raw_location": raw_location,
                "captured_at": captured_at,
            }
        )
    return rows


def _build_company_resolution_coverage_payload(
    *,
    active_rows: list[dict[str, object]],
    target: int,
    include_top_unmapped: bool,
    top_limit: int,
    location_kind: Literal["elevator", "benchmark", "all"] = "elevator",
) -> dict[str, object]:
    by_location: dict[str, dict[str, object]] = {}
    latest_captured_at: datetime | None = None

    for row in active_rows:
        location_name = canonical_location_name(str(row.get("location_name") or row.get("raw_location") or "").strip())
        if not location_name:
            continue
        location_id = row.get("location_id")
        location_key = str(location_id) if location_id is not None else (canonical_key(location_name) or location_name.casefold())
        company_id = row.get("company_id")
        captured_at = row.get("captured_at")
        if isinstance(captured_at, datetime):
            if latest_captured_at is None or captured_at > latest_captured_at:
                latest_captured_at = captured_at

        current = by_location.get(location_key)
        if current is None:
            current = {
                "location": location_name,
                "mapped": company_id is not None,
                "row_count": 0,
                "latest_captured_at": captured_at if isinstance(captured_at, datetime) else None,
                "location_kind": _location_kind_for_name(location_name),
            }
            by_location[location_key] = current
        else:
            if company_id is not None:
                current["mapped"] = True
            latest_for_location = current.get("latest_captured_at")
            if isinstance(captured_at, datetime) and (
                not isinstance(latest_for_location, datetime) or captured_at > latest_for_location
            ):
                current["latest_captured_at"] = captured_at
        current["row_count"] = int(current.get("row_count") or 0) + 1

    values = list(by_location.values())
    active_locations_total = len(values)
    active_elevator_locations_total = sum(1 for row in values if row["location_kind"] == "elevator")
    active_mapped_locations = sum(1 for row in values if bool(row["mapped"]))
    active_mapped_elevator_locations = sum(
        1 for row in values if bool(row["mapped"]) and row["location_kind"] == "elevator"
    )

    payload: dict[str, object] = {
        "latest_captured_at": latest_captured_at.isoformat() if latest_captured_at else None,
        "active_locations_total": active_locations_total,
        "active_elevator_locations_total": active_elevator_locations_total,
        "active_mapped_locations": active_mapped_locations,
        "active_mapped_elevator_locations": active_mapped_elevator_locations,
        "active_unmapped_locations": active_locations_total - active_mapped_locations,
        "active_unmapped_elevator_locations": active_elevator_locations_total - active_mapped_elevator_locations,
        "target_active_mapped_elevators": int(target),
        "target_reached": active_mapped_elevator_locations >= int(target),
    }

    if include_top_unmapped:
        top_rows: list[dict[str, object]] = []
        for entry in values:
            if bool(entry["mapped"]):
                continue
            kind = str(entry["location_kind"])
            if location_kind != "all" and kind != location_kind:
                continue
            latest_for_location = entry.get("latest_captured_at")
            top_rows.append(
                {
                    "location": entry["location"],
                    "row_count": int(entry["row_count"]),
                    "location_kind": kind,
                    "latest_captured_at": latest_for_location.isoformat() if isinstance(latest_for_location, datetime) else None,
                }
            )
        top_rows.sort(
            key=lambda row: (
                -int(row["row_count"]),
                str(row["location"]).casefold(),
            ),
        )
        payload["top_unmapped_rows"] = top_rows[: max(1, int(top_limit))]

    return payload


def _location_kind_for_name(location_name: str | None) -> str:
    return location_kind_for_name(location_name)


def _reject_totals(payload: dict | None) -> dict[str, int]:
    totals, _, _ = _split_reject_breakdown(payload)
    return totals


def _split_reject_breakdown(payload: dict | None) -> tuple[dict[str, int], dict[str, dict[str, int]], dict[str, int]]:
    if not isinstance(payload, dict):
        return {}, {}, {}

    totals: dict[str, int] = {}
    by_source: dict[str, dict[str, int]] = {}
    by_field: dict[str, int] = {}

    nested_source = payload.get("_by_source")
    if isinstance(nested_source, dict):
        for source_name, reason_counts in nested_source.items():
            if not isinstance(reason_counts, dict):
                continue
            bucket: dict[str, int] = {}
            for reason, count in reason_counts.items():
                bucket[str(reason)] = int(count)
            by_source[str(source_name)] = bucket

    nested_field = payload.get("_by_field")
    if isinstance(nested_field, dict):
        for field_name, count in nested_field.items():
            by_field[str(field_name)] = int(count)

    for key, value in payload.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, (int, float)):
            totals[str(key)] = int(value)

    return totals, by_source, by_field
