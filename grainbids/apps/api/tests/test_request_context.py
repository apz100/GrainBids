from __future__ import annotations

from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import request_context
from app.core.request_context import get_request_context, require_admin
from app.db.base import Base
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Organization.__table__, User.__table__])
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _settings(*, mode: str, allow_implicit_org: bool = False, allow_local_header_auth: bool = False):
    return SimpleNamespace(
        auth_context_mode=mode,
        allow_implicit_org=allow_implicit_org,
        allow_local_header_auth=allow_local_header_auth,
    )


def _seed_user(db_session, *, role: str = "member", active: bool = True) -> tuple[uuid.UUID, User]:
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    user = User(
        org_id=org.id,
        email="ops@example.com",
        role=role,
        auth_user_id="auth-123",
        is_active=active,
    )
    db_session.add(user)
    db_session.commit()
    return org.id, user


def test_trusted_proxy_requires_authenticated_user_id(monkeypatch, db_session) -> None:
    org_id, _user = _seed_user(db_session)
    monkeypatch.setattr(request_context, "settings", _settings(mode="trusted_proxy"))

    with pytest.raises(HTTPException) as exc_info:
        get_request_context(x_org_id=str(org_id), x_auth_user_id=None, x_user_email=None, x_user_role=None, db=db_session)

    assert exc_info.value.status_code == 401


def test_trusted_proxy_uses_database_role_instead_of_role_header(monkeypatch, db_session) -> None:
    org_id, user = _seed_user(db_session, role="member")
    monkeypatch.setattr(request_context, "settings", _settings(mode="trusted_proxy"))

    context = get_request_context(
        x_org_id=str(org_id),
        x_auth_user_id=user.auth_user_id,
        x_user_role="owner",
        db=db_session,
    )

    assert context.user_id == user.id
    assert context.user_email == user.email
    assert context.user_role == "member"
    with pytest.raises(HTTPException) as exc_info:
        require_admin(context)
    assert exc_info.value.status_code == 403


def test_local_headers_missing_role_defaults_to_member(monkeypatch, db_session) -> None:
    org_id, _user = _seed_user(db_session)
    monkeypatch.setattr(
        request_context,
        "settings",
        _settings(mode="local_headers", allow_implicit_org=True, allow_local_header_auth=True),
    )

    context = get_request_context(
        x_org_id=str(org_id),
        x_auth_user_id=None,
        x_user_email=None,
        x_user_role=None,
        db=db_session,
    )

    assert context.user_role == "member"
    with pytest.raises(HTTPException) as exc_info:
        require_admin(context)
    assert exc_info.value.status_code == 403


def test_local_headers_can_resolve_seeded_user_role(monkeypatch, db_session) -> None:
    org_id, user = _seed_user(db_session, role="admin")
    monkeypatch.setattr(
        request_context,
        "settings",
        _settings(mode="local_headers", allow_implicit_org=True, allow_local_header_auth=True),
    )

    context = get_request_context(
        x_org_id=str(org_id),
        x_auth_user_id=None,
        x_user_email=user.email,
        x_user_role=None,
        db=db_session,
    )

    assert context.user_id == user.id
    assert context.user_role == "admin"
    assert require_admin(context) == context
