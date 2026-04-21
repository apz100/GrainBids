from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/module")
def module_info():
    return {
        "module": "alerts",
        "primary_models": ["alert_rules", "alerts"],
        "depends_on": ["bids", "watchlists"],
    }
