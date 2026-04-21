from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


@router.get("/module")
def module_info():
    return {
        "module": "watchlists",
        "depends_on": ["bids", "sources"],
    }
