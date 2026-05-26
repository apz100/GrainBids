from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient

from app.api.routes import normalized_prices as normalized_prices_routes
from app.core.request_context import RequestContext, get_request_context
from app.db.session import get_db
from app.main import create_app


def _client_with_preview_payload(monkeypatch, rows: list[dict[str, object]]) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_request_context] = lambda: RequestContext(
        org_id=uuid.uuid4(),
        user_email=None,
        user_role="admin",
    )
    def _db_override():
        yield object()
    app.dependency_overrides[get_db] = _db_override
    monkeypatch.setattr(
        normalized_prices_routes,
        "_load_preview_payload",
        lambda **_kwargs: rows,
    )
    return TestClient(app)


def _preview_rows_fixture() -> list[dict[str, object]]:
    return [
        {
            "id": "e1",
            "location": "Alpha Elevator",
            "company_name": "GLG",
            "commodity_name": "Corn",
            "source_name": "GLG",
            "source_attribution": None,
            "delivery_label": "Oct 2026",
            "futures_month": "Dec 2026",
            "futures_price": 5.2,
            "basis": -0.3,
            "basis_change": 0.02,
            "cash_price_bu": 4.9,
            "cash_price_bu_change": 0.03,
            "cash_price_mt": 193.0,
            "cash_price_mt_change": 1.2,
            "composite_key": "e1",
            "candidate_count": 1,
            "selected_source_key": "glg",
            "canonical_reason": "ranked",
            "is_canonical": True,
            "canonical_rank": 1,
        },
        {
            "id": "b1",
            "location": "Corn Benchmark North",
            "company_name": None,
            "commodity_name": "Corn",
            "source_name": "Ontario Cash Bids",
            "source_attribution": "Ontario Cash Bids",
            "delivery_label": "Oct 2026",
            "futures_month": "Dec 2026",
            "futures_price": 5.1,
            "basis": -0.28,
            "basis_change": 0.01,
            "cash_price_bu": 4.82,
            "cash_price_bu_change": 0.01,
            "cash_price_mt": 189.8,
            "cash_price_mt_change": 0.4,
            "composite_key": "b1",
            "candidate_count": 1,
            "selected_source_key": "ontario cash bids",
            "canonical_reason": "ranked",
            "is_canonical": True,
            "canonical_rank": 1,
        },
    ]


def test_preview_location_kind_elevator_only(monkeypatch) -> None:
    client = _client_with_preview_payload(monkeypatch, _preview_rows_fixture())
    response = client.get("/api/normalized-prices/preview?location_kind=elevator")
    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["rows"]] == ["e1"]


def test_preview_location_kind_benchmark_only(monkeypatch) -> None:
    client = _client_with_preview_payload(monkeypatch, _preview_rows_fixture())
    response = client.get("/api/normalized-prices/preview?location_kind=benchmark")
    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["rows"]] == ["b1"]


def test_preview_location_kind_all_matches_current_behavior(monkeypatch) -> None:
    rows = _preview_rows_fixture()
    client = _client_with_preview_payload(monkeypatch, rows)
    response = client.get("/api/normalized-prices/preview?location_kind=all")
    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["rows"]] == ["e1", "b1"]

    default_response = client.get("/api/normalized-prices/preview")
    assert default_response.status_code == 200
    default_payload = default_response.json()
    assert [row["id"] for row in default_payload["rows"]] == ["e1", "b1"]


def test_preview_invalid_location_kind_returns_422(monkeypatch) -> None:
    client = _client_with_preview_payload(monkeypatch, _preview_rows_fixture())
    response = client.get("/api/normalized-prices/preview?location_kind=invalid")
    assert response.status_code == 422


def test_preview_grouped_location_kind_elevator_only(monkeypatch) -> None:
    client = _client_with_preview_payload(monkeypatch, _preview_rows_fixture())
    response = client.get("/api/normalized-prices/preview-grouped?location_kind=elevator")
    assert response.status_code == 200
    payload = response.json()
    grouped_rows = payload["groups"][0]["rows"]
    assert [row["id"] for row in grouped_rows] == ["e1"]


def test_preview_grouped_location_kind_benchmark_only(monkeypatch) -> None:
    client = _client_with_preview_payload(monkeypatch, _preview_rows_fixture())
    response = client.get("/api/normalized-prices/preview-grouped?location_kind=benchmark")
    assert response.status_code == 200
    payload = response.json()
    grouped_rows = payload["groups"][0]["rows"]
    assert [row["id"] for row in grouped_rows] == ["b1"]


def test_preview_grouped_location_kind_all_matches_default(monkeypatch) -> None:
    rows = _preview_rows_fixture()
    client = _client_with_preview_payload(monkeypatch, rows)
    response_all = client.get("/api/normalized-prices/preview-grouped?location_kind=all")
    assert response_all.status_code == 200
    payload_all = response_all.json()
    ids_all = [row["id"] for row in payload_all["groups"][0]["rows"]]

    response_default = client.get("/api/normalized-prices/preview-grouped")
    assert response_default.status_code == 200
    payload_default = response_default.json()
    ids_default = [row["id"] for row in payload_default["groups"][0]["rows"]]
    assert ids_all == ["e1", "b1"]
    assert ids_default == ids_all


def test_preview_grouped_invalid_location_kind_returns_422(monkeypatch) -> None:
    client = _client_with_preview_payload(monkeypatch, _preview_rows_fixture())
    response = client.get("/api/normalized-prices/preview-grouped?location_kind=invalid")
    assert response.status_code == 422


@dataclass
class _FakeExecuteResult:
    rows: list | None = None
    one_value: tuple[object, object] | None = None
    scalar_value: int | None = None

    def all(self):
        return self.rows or []

    def one(self):
        if self.one_value is None:
            raise AssertionError("one() requested with no one_value configured")
        return self.one_value

    def scalar_one(self):
        if self.scalar_value is None:
            raise AssertionError("scalar_one() requested with no scalar_value configured")
        return self.scalar_value


def _fake_top_mover_row(*, location: str, source_name: str):
    return (
        SimpleNamespace(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            company_id=None,
            location=location,
            commodity_name="Corn",
            source_name=source_name,
            basis=Decimal("-0.25"),
            basis_change=Decimal("0.02"),
            cash_price_bu=Decimal("4.80"),
            cash_price_bu_change=Decimal("0.03"),
            cash_price_mt=Decimal("189.00"),
            cash_price_mt_change=Decimal("1.20"),
        ),
        SimpleNamespace(captured_at=datetime.now(timezone.utc)),
    )


def _client_with_kind_aware_db(monkeypatch, db_obj) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_request_context] = lambda: RequestContext(
        org_id=uuid.uuid4(),
        user_email=None,
        user_role="admin",
    )
    def _db_override():
        yield db_obj
    app.dependency_overrides[get_db] = _db_override
    return TestClient(app)


def _patch_location_kind_capture(monkeypatch):
    kind_state = {"value": "all"}
    original_build_filters = normalized_prices_routes._build_filters

    def _build_filters_with_capture(*args, **kwargs):
        kind_state["value"] = kwargs.get("location_kind", "all")
        return original_build_filters(*args, **kwargs)

    monkeypatch.setattr(normalized_prices_routes, "_build_filters", _build_filters_with_capture)
    return kind_state


def test_top_movers_location_kind_elevator_only(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def execute(self, _statement):
            kind = kind_state["value"]
            if kind == "elevator":
                rows = [_fake_top_mover_row(location="Alpha Elevator", source_name="GLG")]
            elif kind == "benchmark":
                rows = [_fake_top_mover_row(location="Corn Benchmark North", source_name="Ontario Cash Bids")]
            else:
                rows = [
                    _fake_top_mover_row(location="Alpha Elevator", source_name="GLG"),
                    _fake_top_mover_row(location="Corn Benchmark North", source_name="Ontario Cash Bids"),
                ]
            return _FakeExecuteResult(rows=rows)

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response = client.get("/api/normalized-prices/top-movers?location_kind=elevator")
    assert response.status_code == 200
    payload = response.json()
    assert [row["location"] for row in payload["rows"]] == ["Alpha Elevator"]


def test_top_movers_location_kind_benchmark_only(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def execute(self, _statement):
            kind = kind_state["value"]
            if kind == "elevator":
                rows = [_fake_top_mover_row(location="Alpha Elevator", source_name="GLG")]
            elif kind == "benchmark":
                rows = [_fake_top_mover_row(location="Corn Benchmark North", source_name="Ontario Cash Bids")]
            else:
                rows = [
                    _fake_top_mover_row(location="Alpha Elevator", source_name="GLG"),
                    _fake_top_mover_row(location="Corn Benchmark North", source_name="Ontario Cash Bids"),
                ]
            return _FakeExecuteResult(rows=rows)

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response = client.get("/api/normalized-prices/top-movers?location_kind=benchmark")
    assert response.status_code == 200
    payload = response.json()
    assert [row["location"] for row in payload["rows"]] == ["Corn Benchmark North"]


def test_top_movers_location_kind_all_matches_default(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def execute(self, _statement):
            kind = kind_state["value"]
            if kind == "elevator":
                rows = [_fake_top_mover_row(location="Alpha Elevator", source_name="GLG")]
            elif kind == "benchmark":
                rows = [_fake_top_mover_row(location="Corn Benchmark North", source_name="Ontario Cash Bids")]
            else:
                rows = [
                    _fake_top_mover_row(location="Alpha Elevator", source_name="GLG"),
                    _fake_top_mover_row(location="Corn Benchmark North", source_name="Ontario Cash Bids"),
                ]
            return _FakeExecuteResult(rows=rows)

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response_all = client.get("/api/normalized-prices/top-movers?location_kind=all")
    assert response_all.status_code == 200
    all_locations = [row["location"] for row in response_all.json()["rows"]]

    response_default = client.get("/api/normalized-prices/top-movers")
    assert response_default.status_code == 200
    default_locations = [row["location"] for row in response_default.json()["rows"]]
    assert all_locations == ["Alpha Elevator", "Corn Benchmark North"]
    assert default_locations == all_locations


def test_top_movers_invalid_location_kind_returns_422(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def execute(self, _statement):
            _ = kind_state["value"]
            return _FakeExecuteResult(rows=[])

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response = client.get("/api/normalized-prices/top-movers?location_kind=invalid")
    assert response.status_code == 422


def test_summary_location_kind_elevator_only(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def __init__(self):
            self._calls = 0

        def execute(self, _statement):
            self._calls += 1
            if self._calls == 1:
                kind = kind_state["value"]
                if kind == "elevator":
                    return _FakeExecuteResult(one_value=(Decimal("-0.21"), 2))
                if kind == "benchmark":
                    return _FakeExecuteResult(one_value=(Decimal("-0.31"), 3))
                return _FakeExecuteResult(one_value=(Decimal("-0.27"), 5))
            if self._calls == 2:
                return _FakeExecuteResult(scalar_value=4)
            return _FakeExecuteResult(scalar_value=7)

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response = client.get("/api/normalized-prices/summary?location_kind=elevator")
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 2


def test_summary_location_kind_benchmark_only(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def __init__(self):
            self._calls = 0

        def execute(self, _statement):
            self._calls += 1
            if self._calls == 1:
                kind = kind_state["value"]
                if kind == "elevator":
                    return _FakeExecuteResult(one_value=(Decimal("-0.21"), 2))
                if kind == "benchmark":
                    return _FakeExecuteResult(one_value=(Decimal("-0.31"), 3))
                return _FakeExecuteResult(one_value=(Decimal("-0.27"), 5))
            if self._calls == 2:
                return _FakeExecuteResult(scalar_value=4)
            return _FakeExecuteResult(scalar_value=7)

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response = client.get("/api/normalized-prices/summary?location_kind=benchmark")
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 3


def test_summary_location_kind_all_matches_default(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def __init__(self):
            self._calls = 0

        def execute(self, _statement):
            self._calls += 1
            if self._calls == 1:
                kind = kind_state["value"]
                if kind == "elevator":
                    return _FakeExecuteResult(one_value=(Decimal("-0.21"), 2))
                if kind == "benchmark":
                    return _FakeExecuteResult(one_value=(Decimal("-0.31"), 3))
                return _FakeExecuteResult(one_value=(Decimal("-0.27"), 5))
            if self._calls == 2:
                return _FakeExecuteResult(scalar_value=4)
            return _FakeExecuteResult(scalar_value=7)

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response_all = client.get("/api/normalized-prices/summary?location_kind=all")
    assert response_all.status_code == 200
    payload_all = response_all.json()

    default_client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response_default = default_client.get("/api/normalized-prices/summary")
    assert response_default.status_code == 200
    payload_default = response_default.json()

    assert payload_all["row_count"] == 5
    assert payload_default["row_count"] == payload_all["row_count"]


def test_summary_invalid_location_kind_returns_422(monkeypatch) -> None:
    kind_state = _patch_location_kind_capture(monkeypatch)

    class _FakeDb:
        def execute(self, _statement):
            _ = kind_state["value"]
            return _FakeExecuteResult(one_value=(Decimal("-0.27"), 5))

    client = _client_with_kind_aware_db(monkeypatch, _FakeDb())
    response = client.get("/api/normalized-prices/summary?location_kind=invalid")
    assert response.status_code == 422
