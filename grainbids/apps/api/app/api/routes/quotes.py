from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
import pandas as pd
from sqlalchemy import Select, and_, desc, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.quote_run import QuoteRun
from app.models.source import Source


router = APIRouter(prefix="/api/quotes", tags=["quotes"])

EXPORT_ROOT = Path(__file__).resolve().parents[3] / "exports"


@router.get("/module")
def module_info():
    return {
        "module": "quotes",
        "primary_routes": ["/api/quotes/runs", "/api/quotes/export", "/api/quotes/runs/{id}/download"],
    }


@router.get("/runs")
def list_quote_runs(
    limit: int = Query(50, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(QuoteRun).where(QuoteRun.org_id == context.org_id).order_by(desc(QuoteRun.generated_at)).limit(limit)
    ).scalars().all()
    return {
        "rows": [
            {
                "id": str(row.id),
                "org_id": str(row.org_id),
                "commodity_id": str(row.commodity_id) if row.commodity_id else None,
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
                "assumptions_json": row.assumptions_json,
                "output_file_url": row.output_file_url,
                "status": "completed" if row.output_file_url else "pending",
            }
            for row in rows
        ]
    }


@router.post("/runs")
def create_quote_run(
    commodity_id: uuid.UUID | None = Query(None),
    output_file_url: str | None = Query(None),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    assumptions = {"created_via": "api", "commodity_id": str(commodity_id) if commodity_id else None}
    row = QuoteRun(
        org_id=context.org_id,
        commodity_id=commodity_id,
        assumptions_json=assumptions,
        output_file_url=output_file_url,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "status": "completed" if row.output_file_url else "pending",
    }


@router.post("/export")
def export_quotes(
    export_format: str = Query("csv", pattern="^(csv|xlsx)$"),
    commodity: str | None = Query(None),
    location: str | None = Query(None),
    source_name: str | None = Query(None),
    captured_date: date | None = Query(None),
    trucking_cost_bu: float = Query(0.0),
    trucking_cost_mt: float = Query(0.0),
    limit: int = Query(2000, ge=1, le=20000),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = _load_quote_rows(
        db,
        org_id=context.org_id,
        commodity=commodity,
        location=location,
        source_name=source_name,
        captured_date=captured_date,
        limit=limit,
    )
    if not rows:
        raise HTTPException(status_code=400, detail="No rows match the selected quote filters")

    table_rows = [_serialize_export_row(row, trucking_cost_bu=trucking_cost_bu, trucking_cost_mt=trucking_cost_mt) for row in rows]
    file_name = _build_export_file_name(context.org_id, export_format=export_format)
    output_path = EXPORT_ROOT / file_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(table_rows)
    if export_format == "csv":
        frame.to_csv(output_path, index=False)
    else:
        frame.to_excel(output_path, index=False)

    quote_run = QuoteRun(
        org_id=context.org_id,
        assumptions_json={
            "commodity": commodity,
            "location": location,
            "source_name": source_name,
            "captured_date": captured_date.isoformat() if captured_date else None,
            "trucking_cost_bu": trucking_cost_bu,
            "trucking_cost_mt": trucking_cost_mt,
            "row_count": len(table_rows),
            "export_format": export_format,
        },
        output_file_url=f"/api/quotes/runs/{file_name}",
    )
    db.add(quote_run)
    db.commit()
    db.refresh(quote_run)

    return {
        "quote_run_id": str(quote_run.id),
        "row_count": len(table_rows),
        "download_url": f"/api/quotes/runs/{quote_run.id}/download",
        "file_name": file_name,
    }


@router.get("/runs/{quote_run_id}/download")
def download_quote_export(
    quote_run_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(QuoteRun).where(QuoteRun.id == quote_run_id, QuoteRun.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="quote run not found")
    if not row.output_file_url:
        raise HTTPException(status_code=400, detail="quote run has no export file")

    file_name = _extract_file_name(row.output_file_url)
    output_path = EXPORT_ROOT / file_name
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="export file missing")

    media_type = "text/csv" if output_path.suffix == ".csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path=output_path, filename=file_name, media_type=media_type)


def _load_quote_rows(
    db: Session,
    *,
    org_id: uuid.UUID,
    commodity: str | None,
    location: str | None,
    source_name: str | None,
    captured_date: date | None,
    limit: int,
):
    query: Select = (
        select(NormalizedPrice, PriceSnapshot, Source)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id)
        .order_by(desc(PriceSnapshot.captured_at), NormalizedPrice.location)
    )
    if commodity:
        query = query.where(NormalizedPrice.commodity_name.ilike(f"%{commodity.strip()}%"))
    if location:
        query = query.where(NormalizedPrice.location.ilike(f"%{location.strip()}%"))
    if source_name:
        query = query.where(NormalizedPrice.source_name.ilike(f"%{source_name.strip()}%"))
    if captured_date:
        start_dt = datetime.combine(captured_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(captured_date, time.max, tzinfo=timezone.utc)
        query = query.where(and_(PriceSnapshot.captured_at >= start_dt, PriceSnapshot.captured_at <= end_dt))
    return db.execute(query.limit(limit)).all()


def _serialize_export_row(
    row,
    *,
    trucking_cost_bu: float,
    trucking_cost_mt: float,
) -> dict:
    price, snapshot, _source = row
    cash_bu = _as_float(price.cash_price_bu)
    cash_mt = _as_float(price.cash_price_mt)
    delivered_bu = (cash_bu - trucking_cost_bu) if cash_bu is not None else None
    delivered_mt = (cash_mt - trucking_cost_mt) if cash_mt is not None else None
    return {
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        "location": price.location,
        "source_name": price.source_name,
        "commodity_name": price.commodity_name,
        "delivery_start": price.delivery_start,
        "delivery_end": price.delivery_end,
        "delivery_label": price.delivery_label,
        "futures_month": price.futures_month,
        "futures_price": _as_float(price.futures_price),
        "futures_change": _as_float(getattr(price, "futures_change", None)),
        "basis": _as_float(price.basis),
        "cash_price_bu": cash_bu,
        "cash_price_mt": cash_mt,
        "trucking_cost_bu": trucking_cost_bu,
        "trucking_cost_mt": trucking_cost_mt,
        "delivered_price_bu": delivered_bu,
        "delivered_price_mt": delivered_mt,
        "basis_change": _as_float(price.basis_change),
        "cash_price_bu_change": _as_float(price.cash_price_bu_change),
        "cash_price_mt_change": _as_float(price.cash_price_mt_change),
    }


def _build_export_file_name(org_id: uuid.UUID, *, export_format: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"quotes_{str(org_id)[:8]}_{timestamp}.{export_format}"


def _extract_file_name(output_file_url: str) -> str:
    marker = "/api/quotes/runs/"
    candidate = output_file_url.split(marker, maxsplit=1)[-1]
    candidate = candidate.strip("/")
    if not candidate:
        raise HTTPException(status_code=400, detail="invalid output file URL")
    return candidate


def _as_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)
