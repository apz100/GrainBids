from __future__ import annotations

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
    app.dependency_overrides[get_db] = lambda: iter([object()])
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
