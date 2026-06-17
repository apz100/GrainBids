from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.dialects import sqlite

from app.core.config import settings
from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.main import app
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.commodity import Commodity
from app.models.notification_log import NotificationLog
from app.models.normalized_price import NormalizedPrice
from app.models.organization import Organization
from app.models.price_snapshot import PriceSnapshot
from app.models.saved_search import SavedSearch
from app.models.source import Source
from app.models.watchlist import Watchlist
from app.models.watchlist_automation import WatchlistAutomation
from app.services import alert_notifier as alert_notifier_service
from app.services import watchlist_automation as watchlist_automation_service
from app.services.alert_evaluator import evaluate_alert_rules_for_snapshot
from app.services.alert_notifier import notify_new_alerts


class _FakeResult:
    def __init__(self, rows: list[object]):
        self._rows = rows

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list[object]:
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeQuery:
    def __init__(self, session, model):
        self._session = session
        self._model = model

    def count(self) -> int:
        return len(self._session._store.get(self._model, []))


class _FakeSession:
    def __init__(self):
        self._store: dict[type, list[object]] = {}
        self.queries: list[str] = []

    def add(self, obj):
        self._ensure_identity(obj)
        bucket = self._store.setdefault(type(obj), [])
        bucket[:] = [item for item in bucket if getattr(item, "id", None) != getattr(obj, "id", None)]
        bucket.append(obj)
        return obj

    def delete(self, obj):
        bucket = self._store.get(type(obj), [])
        bucket[:] = [item for item in bucket if item is not obj and getattr(item, "id", None) != getattr(obj, "id", None)]

    def commit(self):
        return None

    def flush(self):
        return None

    def refresh(self, obj):
        return None

    def get(self, model, identity):
        for item in self._store.get(model, []):
            if getattr(item, "id", None) == identity:
                return item
        return None

    def query(self, model):
        return _FakeQuery(self, model)

    def execute(self, statement):
        sql = str(statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
        self.queries.append(sql)

        if "FROM watchlist_automations" in sql:
            return _FakeResult(self._query_watchlist_automations(sql))
        if "FROM watchlists" in sql:
            return _FakeResult(self._query_watchlists(sql))
        if "FROM saved_searches" in sql:
            return _FakeResult(self._query_saved_searches(sql))
        if "FROM alert_rules" in sql and "FROM alerts" not in sql:
            return _FakeResult(self._query_alert_rules(sql))
        if "FROM notification_logs" in sql:
            return _FakeResult(self._query_notification_logs(sql))
        if "FROM alerts" in sql and "JOIN alert_rules" in sql:
            return _FakeResult(self._query_alert_notification_pairs(sql))
        if "FROM price_snapshots" in sql and "JOIN sources" in sql:
            return _FakeResult(self._query_snapshot_source(sql))
        if "FROM normalized_prices" in sql:
            return _FakeResult(self._query_normalized_prices(sql))
        return _FakeResult([])

    def _query_watchlist_automations(self, sql: str) -> list[WatchlistAutomation]:
        rows = list(self._store.get(WatchlistAutomation, []))
        org_id = _extract_uuid(sql, "watchlist_automations.org_id")
        watchlist_id = _extract_uuid(sql, "watchlist_automations.watchlist_id")
        if org_id is not None:
            rows = [row for row in rows if row.org_id == org_id]
        if watchlist_id is not None:
            rows = [row for row in rows if row.watchlist_id == watchlist_id]
        rows.sort(key=lambda row: (row.updated_at or datetime.min.replace(tzinfo=timezone.utc), row.id), reverse=True)
        return rows

    def _query_watchlists(self, sql: str) -> list[Watchlist]:
        rows = list(self._store.get(Watchlist, []))
        org_id = _extract_uuid(sql, "watchlists.org_id")
        watchlist_id = _extract_uuid(sql, "watchlists.id")
        if org_id is not None:
            rows = [row for row in rows if row.org_id == org_id]
        if watchlist_id is not None:
            rows = [row for row in rows if row.id == watchlist_id]
        rows.sort(key=lambda row: (row.updated_at or datetime.min.replace(tzinfo=timezone.utc), row.id), reverse=True)
        return rows

    def _query_saved_searches(self, sql: str) -> list[SavedSearch]:
        rows = list(self._store.get(SavedSearch, []))
        saved_search_id = _extract_uuid(sql, "saved_searches.id")
        if saved_search_id is not None:
            rows = [row for row in rows if row.id == saved_search_id]
        return rows

    def _query_alert_rules(self, sql: str) -> list[AlertRule]:
        rows = list(self._store.get(AlertRule, []))
        org_id = _extract_uuid(sql, "alert_rules.org_id")
        alert_rule_id = _extract_uuid(sql, "alert_rules.id")
        if org_id is not None:
            rows = [row for row in rows if row.org_id == org_id and row.is_active]
        if alert_rule_id is not None:
            rows = [row for row in rows if row.id == alert_rule_id]
        rows.sort(key=lambda row: (row.created_at or datetime.min.replace(tzinfo=timezone.utc), row.id))
        return rows

    def _query_notification_logs(self, sql: str) -> list[NotificationLog]:
        rows = list(self._store.get(NotificationLog, []))
        org_id = _extract_uuid(sql, "notification_logs.org_id")
        channel = _extract_string(sql, "notification_logs.channel")
        if org_id is not None:
            rows = [row for row in rows if row.org_id == org_id]
        if channel is not None:
            rows = [row for row in rows if row.channel == channel]
        rows.sort(key=lambda row: (row.created_at or datetime.min.replace(tzinfo=timezone.utc), row.id), reverse=True)
        limit = _extract_limit(sql)
        return rows[:limit] if limit is not None else rows

    def _query_alert_notification_pairs(self, sql: str) -> list[tuple[Alert, AlertRule]]:
        rows = list(self._store.get(Alert, []))
        alert_ids = _extract_uuid_list(sql, "alerts.id IN")
        if alert_ids:
            rows = [row for row in rows if row.id in alert_ids]
        pairs: list[tuple[Alert, AlertRule]] = []
        for alert in rows:
            rule = self.get(AlertRule, alert.alert_rule_id)
            if rule is not None:
                pairs.append((alert, rule))
        return pairs

    def _query_snapshot_source(self, sql: str) -> list[tuple[PriceSnapshot, Source]]:
        snapshot_id = _extract_uuid(sql, "price_snapshots.id")
        if snapshot_id is None:
            return []
        snapshot = self.get(PriceSnapshot, snapshot_id)
        if snapshot is None:
            return []
        source = self.get(Source, snapshot.source_id)
        if source is None:
            return []
        return [(snapshot, source)]

    def _query_normalized_prices(self, sql: str) -> list[NormalizedPrice]:
        snapshot_id = _extract_uuid(sql, "normalized_prices.snapshot_id")
        rows = list(self._store.get(NormalizedPrice, []))
        if snapshot_id is not None:
            rows = [row for row in rows if row.snapshot_id == snapshot_id]
        return rows

    def _ensure_identity(self, obj) -> None:
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        for attr in ("created_at", "updated_at"):
            if hasattr(obj, attr) and getattr(obj, attr, None) is None:
                setattr(obj, attr, now)
        if hasattr(obj, "triggered_at") and getattr(obj, "triggered_at", None) is None:
            obj.triggered_at = now


@contextmanager
def _client_with_context(session, *, org_id: uuid.UUID, role: str = "admin"):
    context = RequestContext(org_id=org_id, user_email="ops@example.com", user_role=role)
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_org(session) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Org")
    session.add(org)
    return org


def _seed_source(session, *, org_id: uuid.UUID, name: str = "GLG") -> Source:
    source = Source(id=uuid.uuid4(), org_id=org_id, name=name, source_type="manual")
    session.add(source)
    return source


def _seed_commodity(session, *, name: str = "Corn") -> Commodity:
    commodity = Commodity(id=uuid.uuid4(), name=name)
    session.add(commodity)
    return commodity


def _seed_snapshot_with_row(
    session,
    *,
    source: Source,
    commodity: Commodity,
    location: str = "Brinston",
    source_name: str = "GLG",
) -> tuple[PriceSnapshot, NormalizedPrice]:
    snapshot = PriceSnapshot(
        id=uuid.uuid4(),
        source_id=source.id,
        commodity_id=commodity.id,
        captured_at=datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc),
    )
    session.add(snapshot)
    row = NormalizedPrice(
        id=uuid.uuid4(),
        snapshot_id=snapshot.id,
        location=location,
        commodity_name=commodity.name,
        source_name=source_name,
        delivery_label="May 2026",
        futures_month="May 2026",
        futures_price=Decimal("4.25"),
        basis=Decimal("0.55"),
        cash_price_bu=Decimal("4.80"),
        cash_price_mt=Decimal("212.00"),
        composite_key=f"{location}|{commodity.name}|{source_name}|May 2026",
    )
    session.add(row)
    return snapshot, row


def _seed_watchlist(session, *, org_id: uuid.UUID, name: str = "Near Brinston") -> Watchlist:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        org_id=org_id,
        name=name,
        is_active=True,
        filters_json={
            "location": "Brinston",
            "commodity_name": "Corn",
            "source_name": "GLG",
        },
    )
    session.add(watchlist)
    return watchlist


def _seed_automation(session, *, watchlist: Watchlist) -> WatchlistAutomation:
    automation = WatchlistAutomation(
        id=uuid.uuid4(),
        org_id=watchlist.org_id,
        watchlist_id=watchlist.id,
        is_enabled=True,
        digest_enabled=True,
        alert_promotion_enabled=True,
        last_run_at=None,
        last_digest_row_count=None,
        last_error_message=None,
    )
    session.add(automation)
    return automation


def _preview_rows(*, watchlist: Watchlist, snapshot: PriceSnapshot, row: NormalizedPrice) -> list[dict]:
    return [
        {
            "id": str(row.id),
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
            "location": row.location,
            "source_name": row.source_name,
            "commodity_name": row.commodity_name,
            "delivery_label": row.delivery_label,
            "futures_month": row.futures_month,
            "basis": float(row.basis) if row.basis is not None else None,
            "cash_price_bu": float(row.cash_price_bu) if row.cash_price_bu is not None else None,
        }
    ]


def test_watchlist_automation_flow_creates_links_and_digest_history(monkeypatch) -> None:
    session = _FakeSession()
    org = _seed_org(session)
    source = _seed_source(session, org_id=org.id)
    commodity = _seed_commodity(session)
    watchlist = _seed_watchlist(session, org_id=org.id)
    snapshot, row = _seed_snapshot_with_row(session, source=source, commodity=commodity)

    monkeypatch.setattr(settings, "alert_email_enabled", True)
    monkeypatch.setattr(settings, "alert_email_from", "alerts@grainbids.com")
    monkeypatch.setattr(settings, "alert_email_to", "ops@grainbids.com")
    monkeypatch.setattr(settings, "alert_smtp_host", "smtp.example.com")
    monkeypatch.setattr(watchlist_automation_service, "load_watchlist_preview_rows", lambda db, watchlist, limit=30: _preview_rows(watchlist=watchlist, snapshot=snapshot, row=row))
    monkeypatch.setattr(watchlist_automation_service, "send_email_message", lambda **kwargs: None)
    monkeypatch.setattr(alert_notifier_service, "send_email_message", lambda **kwargs: None)

    with _client_with_context(session, org_id=org.id) as client:
        enable_response = client.put(
            f"/api/watchlists/{watchlist.id}/automation?is_enabled=true&digest_enabled=true&alert_promotion_enabled=true"
        )
        assert enable_response.status_code == 200
        automation_payload = enable_response.json()["automation"]
        assert automation_payload["watchlist_id"] == str(watchlist.id)
        assert automation_payload["is_enabled"] is True
        assert automation_payload["digest_enabled"] is True
        assert automation_payload["alert_promotion_enabled"] is True
        assert automation_payload["saved_search_id"] is not None
        assert automation_payload["alert_rule_id"] is not None

        list_response = client.get("/api/watchlists")
        assert list_response.status_code == 200
        listed = next(row for row in list_response.json()["rows"] if row["id"] == str(watchlist.id))
        assert listed["automation"]["linked_saved_search_id"] == automation_payload["saved_search_id"]
        assert listed["automation"]["linked_alert_rule_id"] == automation_payload["alert_rule_id"]

        inspect_response = client.get(f"/api/watchlists/{watchlist.id}/automation")
        assert inspect_response.status_code == 200
        inspect_payload = inspect_response.json()
        assert inspect_payload["automation"]["is_enabled"] is True
        assert inspect_payload["preview_rows"]
        assert inspect_payload["saved_search"]["filters_json"]["location"] == "Brinston"

        digest_response = client.post(f"/api/watchlists/{watchlist.id}/automation/run")
        assert digest_response.status_code == 200
        digest_payload = digest_response.json()["automation_run"]
        assert digest_payload["status"] == "sent"
        assert digest_payload["row_count"] == 1

        automation_after_run = client.get(f"/api/watchlists/{watchlist.id}/automation").json()
        assert automation_after_run["recent_notifications"]
        assert automation_after_run["recent_notifications"][0]["channel"] == "watchlist_digest"
        assert automation_after_run["recent_notifications"][0]["payload_json"]["watchlist_id"] == str(watchlist.id)

        alert_eval = evaluate_alert_rules_for_snapshot(session, snapshot_id=snapshot.id)
        assert alert_eval.created_alerts == 1
        assert len(alert_eval.created_alert_ids) == 1
        notify_new_alerts(session, alert_ids=alert_eval.created_alert_ids)

        notification_logs = client.get("/api/alerts/notification-logs?limit=10")
        assert notification_logs.status_code == 200
        rows = notification_logs.json()["rows"]
        assert {row["channel"] for row in rows} >= {"watchlist_digest", "email"}
        assert any(row["alert_id"] is None and row["channel"] == "watchlist_digest" for row in rows)
        assert any(row["alert_id"] is not None and row["channel"] == "email" for row in rows)

        assert session.query(SavedSearch).count() == 1
        assert session.query(Alert).count() == 1


def test_watchlist_automation_update_requires_admin() -> None:
    session = _FakeSession()
    org = _seed_org(session)
    watchlist = _seed_watchlist(session, org_id=org.id)

    with _client_with_context(session, org_id=org.id, role="member") as client:
        response = client.put(f"/api/watchlists/{watchlist.id}/automation?is_enabled=true")

    assert response.status_code == 403


def _extract_uuid(sql: str, field: str) -> uuid.UUID | None:
    match = re.search(rf"{re.escape(field)}\s*=\s*'([^']+)'", sql)
    return uuid.UUID(match.group(1)) if match else None


def _extract_string(sql: str, field: str) -> str | None:
    match = re.search(rf"{re.escape(field)}\s*=\s*'([^']+)'", sql)
    return match.group(1) if match else None


def _extract_uuid_list(sql: str, prefix: str) -> list[uuid.UUID]:
    match = re.search(rf"{re.escape(prefix)}\s*\(([^)]+)\)", sql)
    if not match:
        return []
    return [uuid.UUID(value) for value in re.findall(r"'([^']+)'", match.group(1))]


def _extract_limit(sql: str) -> int | None:
    match = re.search(r"LIMIT\s+(\d+)", sql)
    return int(match.group(1)) if match else None
