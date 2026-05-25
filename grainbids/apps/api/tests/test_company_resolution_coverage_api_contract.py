from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient

from app.api.routes import ingestion as ingestion_routes
from app.core.request_context import RequestContext, require_admin
from app.db.session import get_db
from app.main import create_app


def _active_rows_fixture() -> list[dict[str, object]]:
    now = datetime.now(timezone.utc)
    benchmark_location_id = uuid.uuid4()
    return [
        {
            "location_id": uuid.uuid4(),
            "location_name": "Zeta Elevator",
            "company_id": None,
            "raw_location": "Zeta Elevator",
            "captured_at": now - timedelta(minutes=3),
        },
        {
            "location_id": uuid.uuid4(),
            "location_name": "Alpha Elevator",
            "company_id": None,
            "raw_location": "Alpha Elevator",
            "captured_at": now - timedelta(minutes=2),
        },
        {
            "location_id": benchmark_location_id,
            "location_name": "Corn Benchmark North",
            "company_id": None,
            "raw_location": "Corn Benchmark North",
            "captured_at": now,
        },
        {
            "location_id": benchmark_location_id,
            "location_name": "Corn Benchmark North",
            "company_id": None,
            "raw_location": "Corn Benchmark North",
            "captured_at": now - timedelta(minutes=1),
        },
    ]


def _client_with_overrides(monkeypatch, active_rows: list[dict[str, object]]) -> TestClient:
    app = create_app()

    app.dependency_overrides[require_admin] = lambda: RequestContext(
        org_id=uuid.uuid4(),
        user_email=None,
        user_role="admin",
    )
    app.dependency_overrides[get_db] = lambda: iter([object()])
    monkeypatch.setattr(
        ingestion_routes,
        "_list_active_location_resolution_rows",
        lambda _db, org_id: active_rows,
    )
    return TestClient(app)


def test_company_resolution_coverage_invalid_location_kind_returns_422(monkeypatch) -> None:
    client = _client_with_overrides(monkeypatch, _active_rows_fixture())
    response = client.get("/api/ingestion/company-resolution/coverage?location_kind=invalid")
    assert response.status_code == 422


def test_company_resolution_coverage_defaults_to_elevator_top_rows(monkeypatch) -> None:
    client = _client_with_overrides(monkeypatch, _active_rows_fixture())
    response = client.get("/api/ingestion/company-resolution/coverage")
    assert response.status_code == 200
    payload = response.json()

    assert set(payload.keys()) >= {
        "latest_captured_at",
        "active_locations_total",
        "active_elevator_locations_total",
        "active_mapped_locations",
        "active_mapped_elevator_locations",
        "active_unmapped_locations",
        "active_unmapped_elevator_locations",
        "target_active_mapped_elevators",
        "target_reached",
        "top_unmapped_rows",
    }
    assert payload["target_active_mapped_elevators"] == 65
    assert [row["location_kind"] for row in payload["top_unmapped_rows"]] == ["elevator", "elevator"]
    assert [row["location"] for row in payload["top_unmapped_rows"]] == ["Alpha Elevator", "Zeta Elevator"]


def test_company_resolution_coverage_include_top_unmapped_false(monkeypatch) -> None:
    client = _client_with_overrides(monkeypatch, _active_rows_fixture())
    response = client.get("/api/ingestion/company-resolution/coverage?include_top_unmapped=false")
    assert response.status_code == 200
    payload = response.json()
    assert "top_unmapped_rows" not in payload


def test_company_resolution_coverage_top_limit_and_kind_filter(monkeypatch) -> None:
    client = _client_with_overrides(monkeypatch, _active_rows_fixture())
    response = client.get("/api/ingestion/company-resolution/coverage?location_kind=all&top_limit=1")
    assert response.status_code == 200
    payload = response.json()

    rows = payload["top_unmapped_rows"]
    assert len(rows) == 1
    assert rows[0]["location"] == "Corn Benchmark North"
    assert rows[0]["location_kind"] == "benchmark"
