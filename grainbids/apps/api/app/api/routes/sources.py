from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/sources-module", tags=["sources"])


@router.get("")
def module_info():
    return {
        "module": "sources",
        "primary_routes": [
            "/api/sources",
            "/api/market-data/sources",
            "/api/market-data/refresh",
        ],
    }
