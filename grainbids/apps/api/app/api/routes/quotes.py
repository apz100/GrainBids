from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
from app.models.quote_run import QuoteRun


router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("/module")
def module_info():
    return {
        "module": "quotes",
        "primary_routes": ["/api/quotes/runs"],
    }


@router.get("/runs")
def list_quote_runs(
    org_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    resolved_org = org_id or _default_org_id(db)
    rows = db.execute(
        select(QuoteRun).where(QuoteRun.org_id == resolved_org).order_by(desc(QuoteRun.generated_at)).limit(limit)
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
    org_id: uuid.UUID | None = Query(None),
    commodity_id: uuid.UUID | None = Query(None),
    output_file_url: str | None = Query(None),
    db: Session = Depends(get_db),
):
    resolved_org = org_id or _default_org_id(db)
    assumptions = {"created_via": "api", "commodity_id": str(commodity_id) if commodity_id else None}
    row = QuoteRun(
        org_id=resolved_org,
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


def _default_org_id(db: Session) -> uuid.UUID:
    org = db.execute(select(Organization).order_by(Organization.created_at.asc()).limit(1)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=400, detail="No organization exists. Create one first.")
    return org.id
