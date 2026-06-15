from __future__ import annotations

from dataclasses import dataclass
import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User


ADMIN_ROLES = {"admin", "owner"}
VALID_ROLES = ADMIN_ROLES | {"member"}


@dataclass(frozen=True)
class RequestContext:
    org_id: uuid.UUID
    user_email: str | None
    user_role: str
    user_id: uuid.UUID | None = None
    auth_user_id: str | None = None


def get_request_context(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_auth_user_id: str | None = Header(default=None, alias="X-Auth-User-Id"),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: Session = Depends(get_db),
) -> RequestContext:
    resolved_org = _resolve_org_id(db, x_org_id)
    auth_user_id = (x_auth_user_id or "").strip()

    if settings.auth_context_mode == "trusted_proxy":
        if not auth_user_id:
            raise HTTPException(status_code=401, detail="X-Auth-User-Id header is required")
        return _context_from_user_row(db, org_id=resolved_org, auth_user_id=auth_user_id)

    return _local_header_context(
        db,
        org_id=resolved_org,
        auth_user_id=auth_user_id or None,
        user_email=(x_user_email or "").strip() or None,
        user_role=(x_user_role or "").strip().lower() or None,
    )


def require_admin(context: RequestContext = Depends(get_request_context)) -> RequestContext:
    if context.user_role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    return context


def _context_from_user_row(db: Session, *, org_id: uuid.UUID, auth_user_id: str) -> RequestContext:
    user = db.execute(
        select(User).where(
            User.org_id == org_id,
            User.auth_user_id == auth_user_id,
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Authenticated user was not found for this organization")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Authenticated user is inactive")
    return _build_user_context(org_id=org_id, user=user, auth_user_id=auth_user_id)


def _local_header_context(
    db: Session,
    *,
    org_id: uuid.UUID,
    auth_user_id: str | None,
    user_email: str | None,
    user_role: str | None,
) -> RequestContext:
    user = _lookup_local_user(db, org_id=org_id, auth_user_id=auth_user_id, user_email=user_email)
    if user is not None:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Authenticated user is inactive")
        return _build_user_context(org_id=org_id, user=user, auth_user_id=auth_user_id)

    if not settings.allow_local_header_auth:
        raise HTTPException(status_code=401, detail="Authenticated user was not found for this organization")

    role = _normalize_role(user_role)
    return RequestContext(
        org_id=org_id,
        user_id=None,
        user_email=user_email,
        user_role=role or "member",
        auth_user_id=auth_user_id,
    )


def _lookup_local_user(
    db: Session,
    *,
    org_id: uuid.UUID,
    auth_user_id: str | None,
    user_email: str | None,
) -> User | None:
    if auth_user_id:
        user = db.execute(
            select(User).where(
                User.org_id == org_id,
                User.auth_user_id == auth_user_id,
            )
        ).scalar_one_or_none()
        if user is not None:
            return user
    if user_email:
        return db.execute(
            select(User).where(
                User.org_id == org_id,
                User.email == user_email,
            )
        ).scalar_one_or_none()
    return None


def _build_user_context(*, org_id: uuid.UUID, user: User, auth_user_id: str | None) -> RequestContext:
    role = _normalize_role(user.role)
    return RequestContext(
        org_id=org_id,
        user_id=user.id,
        user_email=user.email,
        user_role=role or "member",
        auth_user_id=auth_user_id or user.auth_user_id,
    )


def _normalize_role(role: str | None) -> str | None:
    normalized = (role or "").strip().lower()
    if not normalized:
        return None
    if normalized not in VALID_ROLES:
        raise HTTPException(status_code=403, detail="Unsupported user role")
    return normalized


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
