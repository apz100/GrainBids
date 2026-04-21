from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/bids", tags=["bids"])


@router.get("/module")
def module_info():
    return {
        "module": "bids",
        "primary_routes": [
            "/api/normalized-prices",
            "/api/normalized-prices/summary",
            "/api/normalized-prices/top-movers",
        ],
    }
