from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("/module")
def module_info():
    return {
        "module": "quotes",
        "primary_models": ["quote_runs"],
        "depends_on": ["bids"],
    }
