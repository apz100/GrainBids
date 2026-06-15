from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

from sqlalchemy import and_, select
from sqlalchemy.dialects import postgresql

from app.api.routes.normalized_prices import (
    _coalesce_zero,
    _canonical_source_filter_values,
    _build_origin_radius_filters,
    _display_company_name,
    _display_company_name_for_row,
    _serialize_preview_row,
    _trusted_company_name,
    _source_attribution_name,
)


def test_canonical_source_filter_values_normalize_alias_to_canonical_key() -> None:
    assert _canonical_source_filter_values("Ontario Daily File") == ["ontario daily file", "ontario cash bids"]


def test_canonical_source_filter_values_keep_company_alias_and_canonical() -> None:
    assert _canonical_source_filter_values("glg") == ["glg", "great lakes grain"]


def test_display_company_name_hides_aggregator_source() -> None:
    assert _display_company_name("Agricharts") is None
    assert _source_attribution_name("Agricharts") == "Agricharts"


def test_display_company_name_keeps_real_company_source() -> None:
    assert _display_company_name("GLG") == "Great Lakes Grain"
    assert _display_company_name("LAC") == "London Agricultural Commodities"
    assert _display_company_name("Hensall HDC") == "Hensall Co-operative"
    assert _display_company_name("Snobelen") == "Snobelen Farms"
    assert _source_attribution_name("GLG") is None


def test_display_company_name_location_override_for_aggregator_rows() -> None:
    price = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=None,
        location_id=None,
        location="Ingredion Cardinal",
        source_name="Agricharts",
    )
    display = _display_company_name_for_row(
        price,
        company_name_map={},
        location_company_map={},
    )
    assert display == "Ingredion"


def test_display_company_name_location_override_wins_over_source_display() -> None:
    price = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=None,
        location_id=None,
        location="Embrun Co-op",
        source_name="GLG",
    )
    display = _display_company_name_for_row(
        price,
        company_name_map={},
        location_company_map={},
    )
    assert display == "Embrun Co-op (GLG)"


def test_region_source_never_displays_as_company() -> None:
    assert _display_company_name("Ontario Cash Bids") is None
    assert _trusted_company_name("Ontario Cash Bids") is None
    assert _source_attribution_name("Ontario Cash Bids") == "Ontario Cash Bids"


def test_coalesce_zero_changes_null_to_zero() -> None:
    assert _coalesce_zero(None) == 0.0
    assert _coalesce_zero(0.0) == 0.0
    assert _coalesce_zero(-0.11) == -0.11


def test_serialize_preview_row_includes_basis_last_changed_at() -> None:
    company_id = uuid.uuid4()
    location_id = uuid.uuid4()
    price = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id,
        location_id=location_id,
        location="Vankleek Hill",
        commodity_name="Corn",
        source_name="Agricharts",
        delivery_label="May 2026",
        delivery_end="May 2026",
        delivery_start=None,
        futures_month="July 2026",
        futures_price=Decimal("450.75"),
        futures_change=Decimal("0.15"),
        basis=Decimal("2.30"),
        basis_change=Decimal("0.23"),
        basis_last_changed_at=datetime(2026, 5, 28, 20, 56, 26, tzinfo=timezone.utc),
        cash_price_bu=Decimal("6.86"),
        cash_price_bu_change=Decimal("0.00"),
        cash_price_mt=Decimal("270.10"),
        cash_price_mt_change=Decimal("0.00"),
        composite_key="vankleek hill|corn||may 2026|july 2026",
        canonical_reason="quality",
        is_canonical=True,
        canonical_rank=1,
    )
    snapshot = SimpleNamespace(captured_at=datetime(2026, 5, 29, 14, 9, 55, tzinfo=timezone.utc))
    row = _serialize_preview_row(
        price=price,
        snapshot=snapshot,
        candidate_counts={price.composite_key: 1},
        company_name_map={company_id: "Wilson Farms"},
        location_company_map={},
    )
    assert row["basis_last_changed_at"] == "2026-05-28T20:56:26+00:00"
    assert row["futures_change"] == 0.15


def test_build_origin_radius_filters_compile_to_coordinate_distance_clause() -> None:
    origin_location_id = uuid.uuid4()
    filters = _build_origin_radius_filters(origin_location_id=origin_location_id, radius_miles=50)
    statement = select(1).where(and_(*filters))
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "locations.latitude" in sql
    assert "locations.longitude" in sql
    assert "asin" in sql.lower()
    assert str(origin_location_id) in sql
    assert "50" in sql
