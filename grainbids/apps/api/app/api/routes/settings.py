from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, get_request_context, require_admin
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User


router = APIRouter(prefix="/api/settings", tags=["settings"])


class OrgUpdateRequest(BaseModel):
    name: str | None = None
    plan: str | None = None


class UserRoleUpdateRequest(BaseModel):
    role: str


@router.get("/module")
def module_info():
    return {
        "module": "settings",
        "primary_routes": ["/api/settings/org", "/api/settings/users"],
    }


@router.get("/org")
def get_org(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, context.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "id": str(org.id),
        "name": org.name,
        "plan": org.plan,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


@router.patch("/org")
def update_org(
    payload: OrgUpdateRequest,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, context.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if payload.name is not None:
        org.name = payload.name
    if payload.plan is not None:
        org.plan = payload.plan
    db.commit()
    return {
        "id": str(org.id),
        "name": org.name,
        "plan": org.plan,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


@router.get("/users")
def list_users(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    users = db.execute(
        select(User).where(User.org_id == context.org_id).order_by(User.created_at)
    ).scalars().all()
    return {
        "rows": [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "company_name": u.company_name,
                "auth_user_id": u.auth_user_id,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    }


@router.patch("/users/{user_id}")
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if payload.role not in ("admin", "owner", "member"):
        raise HTTPException(status_code=400, detail="Role must be admin, owner, or member")
    user = db.get(User, user_id)
    if user is None or user.org_id != context.org_id:
        raise HTTPException(status_code=404, detail="User not found in this organization")
    if user.id == context.user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    user.role = payload.role
    db.commit()
    return {"ok": True, "id": str(user.id), "email": user.email, "role": user.role}
