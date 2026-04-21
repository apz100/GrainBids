from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.signal_forecast import SignalForecast


router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/forecast")
def list_forecasts(
    composite_key: str | None = Query(None),
    horizon_minutes: int | None = Query(None, ge=1),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query = select(SignalForecast).order_by(desc(SignalForecast.generated_at))
    if composite_key:
        query = query.where(SignalForecast.composite_key == composite_key.strip().lower())
    if horizon_minutes is not None:
        query = query.where(SignalForecast.horizon_minutes == horizon_minutes)

    rows = db.execute(query.limit(limit)).scalars().all()
    return {
        "rows": [
            {
                "id": str(row.id),
                "composite_key": row.composite_key,
                "horizon_minutes": row.horizon_minutes,
                "basis_forecast": float(row.basis_forecast) if row.basis_forecast is not None else None,
                "cash_price_bu_forecast": float(row.cash_price_bu_forecast) if row.cash_price_bu_forecast is not None else None,
                "cash_price_mt_forecast": float(row.cash_price_mt_forecast) if row.cash_price_mt_forecast is not None else None,
                "confidence_low": float(row.confidence_low) if row.confidence_low is not None else None,
                "confidence_high": float(row.confidence_high) if row.confidence_high is not None else None,
                "confidence_score": float(row.confidence_score) if row.confidence_score is not None else None,
                "model_version": row.model_version,
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            }
            for row in rows
        ]
    }


@router.get("/health")
def signals_health(db: Session = Depends(get_db)):
    latest = db.execute(select(func.max(SignalForecast.generated_at))).scalar_one_or_none()
    count = db.execute(select(func.count(SignalForecast.id))).scalar_one()
    stale_minutes = None
    if latest:
        stale_minutes = int((datetime.now(timezone.utc) - latest).total_seconds() // 60)
    return {
        "forecast_count": int(count or 0),
        "latest_generated_at": latest.isoformat() if latest else None,
        "stale_minutes": stale_minutes,
        "healthy": latest is not None and stale_minutes is not None and stale_minutes < 180,
    }
