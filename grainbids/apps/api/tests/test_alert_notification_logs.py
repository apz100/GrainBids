from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import re
import sys
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.dialects import sqlite

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.request_context import RequestContext  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.core.request_context import get_request_context  # noqa: E402


class _FakeResult:
    def __init__(self, rows: list[SimpleNamespace]):
        self._rows = rows

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[SimpleNamespace], org_id: uuid.UUID):
        self._rows = rows
        self._org_id = org_id
        self.queries: list[str] = []

    def execute(self, statement):
        sql = str(statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
        self.queries.append(sql)
        assert "FROM notification_logs" in sql
        assert f"notification_logs.org_id = '{self._org_id.hex}'" in sql
        assert "ORDER BY notification_logs.created_at DESC, notification_logs.id DESC" in sql
        limit_match = re.search(r"LIMIT (\d+)", sql)
        if limit_match:
            limit = int(limit_match.group(1))
        else:
            limit = len(self._rows)
        rows = [row for row in self._rows if row.org_id == self._org_id]
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        return _FakeResult(rows[:limit])


@contextmanager
def _override_dependencies(context: RequestContext, session: _FakeSession):
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_notification_logs_endpoint_returns_org_scoped_delivery_history():
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    other_org_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    context = RequestContext(org_id=org_id, user_email="ops@grainbids.com", user_role="member")
    rows = [
        SimpleNamespace(
            id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            org_id=org_id,
            alert_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            channel="email",
            recipient="ops@grainbids.com",
            status="failed",
            provider_message_id=None,
            error_message="SMTP timeout",
            created_at=datetime(2026, 6, 15, 15, 30, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            org_id=org_id,
            alert_id=None,
            channel="email",
            recipient="alerts@grainbids.com",
            status="sent",
            provider_message_id="msg-123",
            error_message=None,
            created_at=datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
            org_id=other_org_id,
            alert_id=None,
            channel="email",
            recipient="other@grainbids.com",
            status="skipped",
            provider_message_id=None,
            error_message="missing email recipient configuration",
            created_at=datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc),
        ),
    ]
    session = _FakeSession(rows, org_id)

    with _override_dependencies(context, session):
        response = TestClient(app).get("/api/alerts/notification-logs?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert [row["status"] for row in payload["rows"]] == ["failed", "sent"]
    assert payload["rows"][0]["channel"] == "email"
    assert payload["rows"][0]["recipient"] == "ops@grainbids.com"
    assert payload["rows"][0]["provider_message_id"] is None
    assert payload["rows"][0]["error_message"] == "SMTP timeout"
    assert payload["rows"][0]["created_at"] == "2026-06-15T15:30:00+00:00"
    assert payload["rows"][1]["provider_message_id"] == "msg-123"
    assert len(session.queries) == 1
