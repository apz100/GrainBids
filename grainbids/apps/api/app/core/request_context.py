from __future__ import annotations

from dataclasses import dataclass
import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.organization import Organization


@dataclass(frozen=True)
class RequestContext:
    org_id: uuid.UUID
    user_email: str | None
    user_role: str


def get_request_context(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: Session = Depends(get_db),
) -> RequestContext:
    resolved_org = _resolve_org_id(db, x_org_id)
    role = (x_user_role or "").strip().lower()
    if not role:
        role = "admin" if settings.allow_implicit_org else "member"
    return RequestContext(
        org_id=resolved_org,
        user_email=(x_user_email or "").strip() or None,
        user_role=role,
    )


def require_admin(context: RequestContext = Depends(get_request_context)) -> RequestContext:
    if context.user_role not in {"admin", "owner"}:
        raise HTTPException(status_code=403, detail="Admin role required")
    return context


def _resolve_org_id(db: Session, header_value: str | None) -> uuid.UUID:
    if header_value:
        try:
            parsed = uuid.UUID(header_value.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid X-Org-Id header") from exc
        org_exists = db.execute(select(Organization.id).where(Organization.id == parsed)).scalar_one_or_none()
        if org_exists is None:
            raise HTTPException(status_code=404, detail="Organization from X-Org-Id was not found")
        return parsed

    if not settings.allow_implicit_org:
        raise HTTPException(status_code=400, detail="X-Org-Id header is required")

    org = db.execute(select(Organization).order_by(Organization.created_at.asc()).limit(1)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=400, detail="No organization exists. Create one first.")
    return org.id
