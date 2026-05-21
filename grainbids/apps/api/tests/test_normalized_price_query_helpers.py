from __future__ import annotations

from app.api.routes.normalized_prices import (
    _canonical_source_filter_values,
    _display_company_name,
    _trusted_company_name,
    _source_attribution_name,
)


def test_canonical_source_filter_values_normalize_alias_to_canonical_key() -> None:
    assert _canonical_source_filter_values("Ontario Daily File") == ["ontario daily file", "ontario cash bids"]


def test_canonical_source_filter_values_keep_company_alias_and_canonical() -> None:
    assert _canonical_source_filter_values("glg") == ["glg"]


def test_display_company_name_hides_aggregator_source() -> None:
    assert _display_company_name("Agricharts") is None
    assert _source_attribution_name("Agricharts") == "Agricharts"


def test_display_company_name_keeps_real_company_source() -> None:
    assert _display_company_name("GLG") == "GLG"
    assert _source_attribution_name("GLG") is None


def test_region_source_never_displays_as_company() -> None:
    assert _display_company_name("Ontario Cash Bids") is None
    assert _trusted_company_name("Ontario Cash Bids") is None
    assert _source_attribution_name("Ontario Cash Bids") == "Ontario Cash Bids"
