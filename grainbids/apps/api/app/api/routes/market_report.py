from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, require_admin
from app.db.session import get_db
from app.services.market_report import build_market_report


router = APIRouter(prefix="/api/market-report", tags=["market-report"])


@router.get("/preview")
def preview_market_report(
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return build_market_report(db, org_id=context.org_id).as_dict()
