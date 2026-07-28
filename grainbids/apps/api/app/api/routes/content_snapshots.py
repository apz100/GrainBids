from __future__ import annotations

from hmac import compare_digest
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.content_snapshot_export import DEFAULT_COMMODITIES, build_content_snapshot


router = APIRouter(prefix="/api/content/v1", tags=["content-snapshots"])
_bearer = HTTPBearer(auto_error=False)


def require_content_snapshot_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    configured_keys = settings.content_snapshot_api_keys_list
    if not configured_keys or not settings.content_snapshot_org_id.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Content snapshot interface is not configured",
        )
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not any(compare_digest(credentials.credentials, configured) for configured in configured_keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/snapshots/cash-bids")
def get_cash_bid_content_snapshot(
    region: str | None = Query(default=None, min_length=2, max_length=120),
    commodity: list[str] | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=5000),
    _access: None = Depends(require_content_snapshot_access),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        org_id = uuid.UUID(settings.content_snapshot_org_id.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CONTENT_SNAPSHOT_ORG_ID is invalid",
        ) from exc

    return build_content_snapshot(
        db,
        org_id=org_id,
        region=region,
        commodities=commodity or DEFAULT_COMMODITIES,
        limit=limit,
        currency_code=settings.content_snapshot_currency_code,
        max_age_minutes=settings.content_snapshot_max_age_minutes,
    )
