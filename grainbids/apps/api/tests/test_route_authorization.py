from __future__ import annotations

from contextlib import contextmanager
import uuid

from fastapi.testclient import TestClient

from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.main import app


@contextmanager
def _member_context():
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    context = RequestContext(org_id=org_id, user_email="member@example.com", user_role="member")
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_saved_search_mutation_requires_admin() -> None:
    with _member_context():
        response = TestClient(app).post("/api/saved-searches?name=Basis")

    assert response.status_code == 403


def test_watchlist_mutation_requires_admin() -> None:
    with _member_context():
        response = TestClient(app).post("/api/watchlists?name=Basis")

    assert response.status_code == 403


def test_alert_status_mutation_requires_admin() -> None:
    alert_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    with _member_context():
        response = TestClient(app).patch(f"/api/alerts/{alert_id}/status?status=acknowledged")

    assert response.status_code == 403


def test_alert_ack_mutation_requires_admin() -> None:
    alert_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    with _member_context():
        response = TestClient(app).post(f"/api/alerts/{alert_id}/ack")

    assert response.status_code == 403
