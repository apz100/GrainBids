from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.request_context import RequestContext, get_request_context
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.commodity import Commodity
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.organization import Organization
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_key, location_kind_for_name


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "TEXT"


@pytest.fixture()
def db_backed_client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    seed_session = SessionLocal()
    seeded_org_id = _seed_normalized_market_dataset(seed_session)
    seed_session.close()

    app = create_app()

    def _request_context_override():
        return RequestContext(
            org_id=seeded_org_id,
            user_email=None,
            user_role="admin",
        )

    def _db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_request_context] = _request_context_override
    app.dependency_overrides[get_db] = _db_override

    try:
        with TestClient(app) as client:
            yield client
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_normalized_market_dataset(db: Session) -> uuid.UUID:
    org = Organization(name="Test Org", plan="trial")
    commodity = Commodity(name="Corn", unit="bu")
    db.add_all([org, commodity])
    db.flush()
    source_elevator = Source(org_id=org.id, name="GLG", source_type="manual", is_active=True)
    source_benchmark = Source(org_id=org.id, name="Ontario Cash Bids", source_type="file", is_active=True)
    db.add_all([source_elevator, source_benchmark])
    db.flush()

    elevator_locations = [
        Location(org_id=org.id, name="Alpha Elevator", canonical_key=canonical_key("Alpha Elevator") or "alpha elevator", company_id=None, region="ON"),
        Location(org_id=org.id, name="Beta Elevator", canonical_key=canonical_key("Beta Elevator") or "beta elevator", company_id=None, region="ON"),
    ]
    benchmark_locations = [
        Location(
            org_id=org.id,
            name="Corn Benchmark North",
            canonical_key=canonical_key("Corn Benchmark North") or "corn benchmark north",
            company_id=None,
            region="ON",
        ),
        Location(
            org_id=org.id,
            name="Wheat Benchmark South",
            canonical_key=canonical_key("Wheat Benchmark South") or "wheat benchmark south",
            company_id=None,
            region="ON",
        ),
    ]
    db.add_all([*elevator_locations, *benchmark_locations])
    db.flush()

    snap_elevator = PriceSnapshot(
        source_id=source_elevator.id,
        commodity_id=commodity.id,
        captured_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
    )
    snap_benchmark = PriceSnapshot(
        source_id=source_benchmark.id,
        commodity_id=commodity.id,
        captured_at=datetime(2026, 5, 26, 10, 5, tzinfo=timezone.utc),
    )
    db.add_all([snap_elevator, snap_benchmark])
    db.flush()

    rows = [
        _normalized_row(
            snapshot_id=snap_elevator.id,
            location_id=elevator_locations[0].id,
            location="Alpha Elevator",
            source_name=source_elevator.name,
            basis_change=0.02,
            composite_key="alpha|corn|oct-2026|dec-2026",
        ),
        _normalized_row(
            snapshot_id=snap_elevator.id,
            location_id=elevator_locations[1].id,
            location="Beta Elevator",
            source_name=source_elevator.name,
            basis_change=0.03,
            composite_key="beta|corn|oct-2026|dec-2026",
        ),
        _normalized_row(
            snapshot_id=snap_benchmark.id,
            location_id=benchmark_locations[0].id,
            location="Corn Benchmark North",
            source_name=source_benchmark.name,
            basis_change=0.01,
            composite_key="bench-north|corn|oct-2026|dec-2026",
        ),
        _normalized_row(
            snapshot_id=snap_benchmark.id,
            location_id=benchmark_locations[1].id,
            location="Wheat Benchmark South",
            source_name=source_benchmark.name,
            basis_change=0.04,
            composite_key="bench-south|corn|oct-2026|dec-2026",
        ),
    ]
    db.add_all(rows)
    db.flush()

    rule = AlertRule(
        org_id=org.id,
        commodity_id=commodity.id,
        rule_type="basis",
        threshold_value=0.1,
        comparison_operator=">",
        is_active=True,
    )
    db.add(rule)
    db.flush()
    db.add(Alert(alert_rule_id=rule.id, message="test alert", status="open"))
    db.commit()
    return org.id


def _normalized_row(
    *,
    snapshot_id: uuid.UUID,
    location_id: uuid.UUID,
    location: str,
    source_name: str,
    basis_change: float,
    composite_key: str,
) -> NormalizedPrice:
    return NormalizedPrice(
        snapshot_id=snapshot_id,
        company_id=None,
        location_id=location_id,
        location=location,
        commodity_name="Corn",
        source_name=source_name,
        delivery_label="Oct 2026",
        delivery_start="2026-10-01",
        delivery_end="Oct 2026",
        futures_month="Dec 2026",
        futures_price=5.11,
        basis=-0.22,
        cash_price_bu=4.89,
        cash_price_mt=192.45,
        basis_change=basis_change,
        cash_price_bu_change=0.02,
        cash_price_mt_change=0.8,
        is_canonical=True,
        canonical_rank=1,
        canonical_reason="test",
        composite_key=composite_key,
    )


def _assert_kind_scope(rows: list[dict[str, object]], expected_kind: str) -> None:
    assert rows
    for row in rows:
        label = str(row.get("location") or "")
        assert location_kind_for_name(label) == expected_kind


def _flatten_group_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    groups = payload.get("groups", [])
    rows: list[dict[str, object]] = []
    for group in groups:
        rows.extend(group.get("rows", []))
    return rows


def test_preview_grouped_location_kind_scopes_with_real_db(db_backed_client: TestClient) -> None:
    elevator = db_backed_client.get("/api/normalized-prices/preview-grouped?location_kind=elevator")
    assert elevator.status_code == 200
    elevator_rows = _flatten_group_rows(elevator.json())
    _assert_kind_scope(elevator_rows, "elevator")

    benchmark = db_backed_client.get("/api/normalized-prices/preview-grouped?location_kind=benchmark")
    assert benchmark.status_code == 200
    benchmark_rows = _flatten_group_rows(benchmark.json())
    _assert_kind_scope(benchmark_rows, "benchmark")

    all_rows = _flatten_group_rows(db_backed_client.get("/api/normalized-prices/preview-grouped?location_kind=all").json())
    default_rows = _flatten_group_rows(db_backed_client.get("/api/normalized-prices/preview-grouped").json())
    assert sorted(str(row["location"]) for row in all_rows) == sorted(str(row["location"]) for row in default_rows)


def test_top_movers_location_kind_scopes_with_real_db(db_backed_client: TestClient) -> None:
    elevator = db_backed_client.get("/api/normalized-prices/top-movers?location_kind=elevator")
    assert elevator.status_code == 200
    elevator_rows = elevator.json()["rows"]
    _assert_kind_scope(elevator_rows, "elevator")

    benchmark = db_backed_client.get("/api/normalized-prices/top-movers?location_kind=benchmark")
    assert benchmark.status_code == 200
    benchmark_rows = benchmark.json()["rows"]
    _assert_kind_scope(benchmark_rows, "benchmark")

    all_rows = db_backed_client.get("/api/normalized-prices/top-movers?location_kind=all").json()["rows"]
    default_rows = db_backed_client.get("/api/normalized-prices/top-movers").json()["rows"]
    assert sorted(str(row["location"]) for row in all_rows) == sorted(str(row["location"]) for row in default_rows)


def test_summary_location_kind_scopes_with_real_db(db_backed_client: TestClient) -> None:
    elevator = db_backed_client.get("/api/normalized-prices/summary?location_kind=elevator")
    assert elevator.status_code == 200
    elevator_payload = elevator.json()

    benchmark = db_backed_client.get("/api/normalized-prices/summary?location_kind=benchmark")
    assert benchmark.status_code == 200
    benchmark_payload = benchmark.json()

    all_payload = db_backed_client.get("/api/normalized-prices/summary?location_kind=all").json()
    default_payload = db_backed_client.get("/api/normalized-prices/summary").json()

    assert int(elevator_payload["row_count"]) == 2
    assert int(benchmark_payload["row_count"]) == 2
    assert int(all_payload["row_count"]) == 4
    assert int(default_payload["row_count"]) == int(all_payload["row_count"])
