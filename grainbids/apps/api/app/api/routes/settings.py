from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/module")
def module_info():
    return {
        "module": "settings",
        "depends_on": ["organizations", "sources", "billing"],
    }
