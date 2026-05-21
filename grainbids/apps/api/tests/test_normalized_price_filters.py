from __future__ import annotations

from app.api.routes.normalized_prices import (
    _build_quality_filters,
    _canonical_and_quality_filters,
    _group_preview_rows_by_delivery,
    _prune_facet_rows,
    _user_visible_market_filters,
)


def test_user_visible_market_filters_extend_canonical_filters() -> None:
    canonical_filters = _canonical_and_quality_filters(False)
    quality_filters = _build_quality_filters()
    combined_filters = _user_visible_market_filters(False)

    assert len(combined_filters) == len(canonical_filters) + len(quality_filters)
    assert len(combined_filters) > len(canonical_filters)


def test_user_visible_market_filters_for_alternates_still_include_quality_gate() -> None:
    combined_filters = _user_visible_market_filters(True)
    quality_filters = _build_quality_filters()

    assert len(combined_filters) >= len(quality_filters)


def test_group_preview_rows_by_delivery_sorts_months_and_limits_rows() -> None:
    groups = _group_preview_rows_by_delivery(
        [
            {"id": "3", "delivery_label": "Jul 2026", "futures_month": None, "cash_price_bu": 5.5, "basis": 0.8, "location": "C"},
            {"id": "1", "delivery_label": "May 2026", "futures_month": None, "cash_price_bu": 6.2, "basis": 1.0, "location": "A"},
            {"id": "2", "delivery_label": "May 2026", "futures_month": None, "cash_price_bu": 6.0, "basis": 0.9, "location": "B"},
        ],
        rows_per_group=1,
    )

    assert [group["label"] for group in groups] == ["May 2026", "Jul 2026"]
    assert groups[0]["row_count"] == 2
    assert len(groups[0]["rows"]) == 1
    assert groups[0]["rows"][0]["id"] == "1"


def test_prune_facet_rows_respects_minimum_market_count() -> None:
    rows = [
        {"id": "1", "name": "GLG", "market_count": 3},
        {"id": "2", "name": "Thin Row", "market_count": 1},
    ]

    pruned = _prune_facet_rows(rows, minimum_market_count=2)

    assert pruned == [{"id": "1", "name": "GLG", "market_count": 3}]
