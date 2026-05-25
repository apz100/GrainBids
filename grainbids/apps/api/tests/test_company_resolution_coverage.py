from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from app.api.routes import ingestion as ingestion_routes
from app.api.routes.ingestion import _build_company_resolution_coverage_payload
from app.core.request_context import RequestContext


def test_company_resolution_coverage_payload_includes_expected_shape_and_defaults() -> None:
    now = datetime.now(timezone.utc)
    mapped_elevator_id = uuid.uuid4()
    unmapped_toledo_id = uuid.uuid4()
    unmapped_feed_mill_id = uuid.uuid4()
    unmapped_other_id = uuid.uuid4()

    payload = _build_company_resolution_coverage_payload(
        active_rows=[
            {
                "location_id": mapped_elevator_id,
                "location_name": "Blenheim Elevator",
                "company_id": uuid.uuid4(),
                "raw_location": "Blenheim Elevator",
                "captured_at": now - timedelta(minutes=30),
            },
            {
                "location_id": unmapped_toledo_id,
                "location_name": "Toledo Corn",
                "company_id": None,
                "raw_location": "Toledo Corn",
                "captured_at": now - timedelta(minutes=20),
            },
            {
                "location_id": unmapped_toledo_id,
                "location_name": "Toledo Corn",
                "company_id": None,
                "raw_location": "Toledo Corn",
                "captured_at": now - timedelta(minutes=10),
            },
            {
                "location_id": unmapped_feed_mill_id,
                "location_name": "River Feed Mill",
                "company_id": None,
                "raw_location": "River Feed Mill",
                "captured_at": now - timedelta(minutes=5),
            },
            {
                "location_id": unmapped_other_id,
                "location_name": "County Yard",
                "company_id": None,
                "raw_location": "County Yard",
                "captured_at": now,
            },
        ],
        target=2,
        include_top_unmapped=True,
        top_limit=25,
    )

    assert payload["latest_captured_at"] == now.isoformat()
    assert payload["active_locations_total"] == 4
    assert payload["active_elevator_locations_total"] == 3
    assert payload["active_mapped_locations"] == 1
    assert payload["active_mapped_elevator_locations"] == 1
    assert payload["active_unmapped_locations"] == 3
    assert payload["active_unmapped_elevator_locations"] == 2
    assert payload["target_active_mapped_elevators"] == 2
    assert payload["target_reached"] is False
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

    top_rows = payload.get("top_unmapped_rows")
    assert isinstance(top_rows, list)
    assert [row["location"] for row in top_rows] == ["Toledo Elevator", "River Feed Mill"]
    assert [row["row_count"] for row in top_rows] == [2, 1]
    assert all(row["location_kind"] == "elevator" for row in top_rows)


def test_company_resolution_coverage_payload_honors_include_top_unmapped_and_target() -> None:
    now = datetime.now(timezone.utc)
    payload = _build_company_resolution_coverage_payload(
        active_rows=[
            {
                "location_id": uuid.uuid4(),
                "location_name": "Toledo Corn",
                "company_id": uuid.uuid4(),
                "raw_location": "Toledo Corn",
                "captured_at": now,
            }
        ],
        target=1,
        include_top_unmapped=False,
        top_limit=10,
    )

    assert payload["target_active_mapped_elevators"] == 1
    assert payload["target_reached"] is True
    assert "top_unmapped_rows" not in payload


def test_company_resolution_coverage_endpoint_respects_top_limit(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    active_rows = [
        {
            "location_id": uuid.uuid4(),
            "location_name": "Toledo Corn",
            "company_id": None,
            "raw_location": "Toledo Corn",
            "captured_at": now,
        },
        {
            "location_id": uuid.uuid4(),
            "location_name": "River Feed Mill",
            "company_id": None,
            "raw_location": "River Feed Mill",
            "captured_at": now - timedelta(minutes=5),
        },
    ]

    monkeypatch.setattr(
        ingestion_routes,
        "_list_active_location_resolution_rows",
        lambda _db, org_id: active_rows,
    )

    payload = ingestion_routes.get_company_resolution_coverage(
        target=65,
        include_top_unmapped=True,
        top_limit=1,
        location_kind="elevator",
        context=RequestContext(org_id=uuid.uuid4(), user_email=None, user_role="admin"),
        db=object(),
    )

    assert payload["target_active_mapped_elevators"] == 65
    assert payload["target_reached"] is False
    assert payload["active_unmapped_elevator_locations"] == 2
    assert [row["location"] for row in payload["top_unmapped_rows"]] == ["River Feed Mill"]


def test_company_resolution_coverage_payload_location_kind_variants_and_sort() -> None:
    now = datetime.now(timezone.utc)
    benchmark_location_id = uuid.uuid4()
    payload = _build_company_resolution_coverage_payload(
        active_rows=[
            {
                "location_id": uuid.uuid4(),
                "location_name": "Alpha Elevator",
                "company_id": None,
                "raw_location": "Alpha Elevator",
                "captured_at": now - timedelta(minutes=5),
            },
            {
                "location_id": uuid.uuid4(),
                "location_name": "Beta Elevator",
                "company_id": None,
                "raw_location": "Beta Elevator",
                "captured_at": now,
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
        ],
        target=65,
        include_top_unmapped=True,
        top_limit=25,
        location_kind="benchmark",
    )

    benchmark_rows = payload["top_unmapped_rows"]
    assert [row["location_kind"] for row in benchmark_rows] == ["benchmark"]
    assert [row["location"] for row in benchmark_rows] == ["Corn Benchmark North"]

    payload_elevator = _build_company_resolution_coverage_payload(
        active_rows=[
            {
                "location_id": uuid.uuid4(),
                "location_name": "Beta Elevator",
                "company_id": None,
                "raw_location": "Beta Elevator",
                "captured_at": now,
            },
            {
                "location_id": uuid.uuid4(),
                "location_name": "Alpha Elevator",
                "company_id": None,
                "raw_location": "Alpha Elevator",
                "captured_at": now,
            },
        ],
        target=65,
        include_top_unmapped=True,
        top_limit=25,
        location_kind="elevator",
    )
    assert [row["location"] for row in payload_elevator["top_unmapped_rows"]] == ["Alpha Elevator", "Beta Elevator"]

    payload_all = _build_company_resolution_coverage_payload(
        active_rows=[
            {
                "location_id": uuid.uuid4(),
                "location_name": "Beta Elevator",
                "company_id": None,
                "raw_location": "Beta Elevator",
                "captured_at": now,
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
        ],
        target=65,
        include_top_unmapped=True,
        top_limit=25,
        location_kind="all",
    )
    assert [row["location"] for row in payload_all["top_unmapped_rows"]] == ["Corn Benchmark North", "Beta Elevator"]
    assert [row["location_kind"] for row in payload_all["top_unmapped_rows"]] == ["benchmark", "elevator"]
