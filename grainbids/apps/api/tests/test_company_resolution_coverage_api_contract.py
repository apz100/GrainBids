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


def test_company_resolution_coverage_invalid_target_returns_422(monkeypatch) -> None:
    client = _client_with_overrides(monkeypatch, _active_rows_fixture())
    response = client.get("/api/ingestion/company-resolution/coverage?target=0")
    assert response.status_code == 422


def test_company_resolution_coverage_invalid_top_limit_returns_422(monkeypatch) -> None:
    client = _client_with_overrides(monkeypatch, _active_rows_fixture())
    response = client.get("/api/ingestion/company-resolution/coverage?top_limit=0")
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


def test_company_resolution_coverage_tie_break_orders_by_location_ascending(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    client = _client_with_overrides(
        monkeypatch,
        [
            {
                "location_id": uuid.uuid4(),
                "location_name": "Zulu Elevator",
                "company_id": None,
                "raw_location": "Zulu Elevator",
                "captured_at": now,
            },
            {
                "location_id": uuid.uuid4(),
                "location_name": "Alpha Elevator",
                "company_id": None,
                "raw_location": "Alpha Elevator",
                "captured_at": now - timedelta(minutes=1),
            },
        ],
    )
    response = client.get("/api/ingestion/company-resolution/coverage?location_kind=elevator")
    assert response.status_code == 200
    payload = response.json()
    assert [row["row_count"] for row in payload["top_unmapped_rows"]] == [1, 1]
    assert [row["location"] for row in payload["top_unmapped_rows"]] == ["Alpha Elevator", "Zulu Elevator"]


def test_company_resolution_coverage_all_kind_mixed_filter_and_ordering(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    benchmark_a_id = uuid.uuid4()
    benchmark_z_id = uuid.uuid4()
    client = _client_with_overrides(
        monkeypatch,
        [
            {
                "location_id": uuid.uuid4(),
                "location_name": "Bravo Elevator",
                "company_id": None,
                "raw_location": "Bravo Elevator",
                "captured_at": now,
            },
            {
                "location_id": benchmark_z_id,
                "location_name": "Wheat Benchmark Z",
                "company_id": None,
                "raw_location": "Wheat Benchmark Z",
                "captured_at": now,
            },
            {
                "location_id": benchmark_z_id,
                "location_name": "Wheat Benchmark Z",
                "company_id": None,
                "raw_location": "Wheat Benchmark Z",
                "captured_at": now - timedelta(minutes=1),
            },
            {
                "location_id": benchmark_a_id,
                "location_name": "Corn Benchmark A",
                "company_id": None,
                "raw_location": "Corn Benchmark A",
                "captured_at": now - timedelta(minutes=2),
            },
            {
                "location_id": benchmark_a_id,
                "location_name": "Corn Benchmark A",
                "company_id": None,
                "raw_location": "Corn Benchmark A",
                "captured_at": now - timedelta(minutes=3),
            },
        ],
    )
    response = client.get("/api/ingestion/company-resolution/coverage?location_kind=all")
    assert response.status_code == 200
    payload = response.json()

    rows = payload["top_unmapped_rows"]
    assert [row["row_count"] for row in rows] == [2, 2, 1]
    assert [row["location"] for row in rows] == ["Corn Benchmark A", "Wheat Benchmark Z", "Bravo Elevator"]
    assert [row["location_kind"] for row in rows] == ["benchmark", "benchmark", "elevator"]


def test_company_resolution_coverage_all_kind_tie_then_top_limit_truncates_after_sort(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    corn_a_id = uuid.uuid4()
    wheat_m_id = uuid.uuid4()
    oats_z_id = uuid.uuid4()
    client = _client_with_overrides(
        monkeypatch,
        [
            {
                "location_id": oats_z_id,
                "location_name": "Oats Benchmark Z",
                "company_id": None,
                "raw_location": "Oats Benchmark Z",
                "captured_at": now,
            },
            {
                "location_id": oats_z_id,
                "location_name": "Oats Benchmark Z",
                "company_id": None,
                "raw_location": "Oats Benchmark Z",
                "captured_at": now - timedelta(minutes=1),
            },
            {
                "location_id": corn_a_id,
                "location_name": "Corn Benchmark A",
                "company_id": None,
                "raw_location": "Corn Benchmark A",
                "captured_at": now - timedelta(minutes=2),
            },
            {
                "location_id": corn_a_id,
                "location_name": "Corn Benchmark A",
                "company_id": None,
                "raw_location": "Corn Benchmark A",
                "captured_at": now - timedelta(minutes=3),
            },
            {
                "location_id": wheat_m_id,
                "location_name": "Wheat Benchmark M",
                "company_id": None,
                "raw_location": "Wheat Benchmark M",
                "captured_at": now - timedelta(minutes=4),
            },
            {
                "location_id": wheat_m_id,
                "location_name": "Wheat Benchmark M",
                "company_id": None,
                "raw_location": "Wheat Benchmark M",
                "captured_at": now - timedelta(minutes=5),
            },
        ],
    )
    response = client.get("/api/ingestion/company-resolution/coverage?location_kind=all&top_limit=2")
    assert response.status_code == 200
    payload = response.json()
    rows = payload["top_unmapped_rows"]

    assert [row["row_count"] for row in rows] == [2, 2]
    assert [row["location"] for row in rows] == ["Corn Benchmark A", "Oats Benchmark Z"]
    assert [row["location_kind"] for row in rows] == ["benchmark", "benchmark"]
