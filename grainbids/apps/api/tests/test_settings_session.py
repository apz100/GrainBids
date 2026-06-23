from __future__ import annotations

from contextlib import contextmanager
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization


class _FakeSession:
    def __init__(self, org: Organization | None):
        self.org = org

    def get(self, model, key):
        if model is Organization and self.org is not None and self.org.id == key:
            return self.org
        return None


@contextmanager
def _session_overrides(context: RequestContext | None, db_session: _FakeSession):
    if context is not None:
        app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_session_bootstrap_returns_current_identity() -> None:
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    org = Organization(id=org_id, name="Test Org", plan="trial")
    context = RequestContext(
        org_id=org_id,
        user_id=user_id,
        auth_user_id="auth-123",
        user_email="ops@example.com",
        user_role="admin",
    )

    with _session_overrides(context, _FakeSession(org)):
        response = TestClient(app).get("/api/settings/session")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "org_id": str(org_id),
        "org_name": "Test Org",
        "user_id": str(user_id),
        "auth_user_id": "auth-123",
        "user_email": "ops@example.com",
        "user_role": "admin",
    }


def test_session_bootstrap_uses_request_context_enforcement() -> None:
    def reject_context():
        raise HTTPException(status_code=401, detail="Auth required")

    with _session_overrides(None, _FakeSession(None)):
        app.dependency_overrides[get_request_context] = reject_context
        response = TestClient(app).get("/api/settings/session")

    assert response.status_code == 401
