from __future__ import annotations

import uuid

from app.models.normalized_price import NormalizedPrice
from app.services.ingestion_diagnostics import summarize_duplicate_candidates
from app.services.source_file_ingestion import _source_file_path_for_reprocess


def _build_row(
    *,
    source_name: str,
    company_id: uuid.UUID | None = None,
    location: str = "Blenheim Corn",
    commodity_name: str = "Corn",
    delivery_end: str = "May 2026",
    futures_month: str = "Jul 2026",
    is_canonical: bool = False,
) -> NormalizedPrice:
    return NormalizedPrice(
        id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        company_id=company_id,
        location_id=None,
        location=location,
        commodity_name=commodity_name,
        source_name=source_name,
        delivery_start=None,
        delivery_end=delivery_end,
        delivery_label=delivery_end,
        futures_month=futures_month,
        futures_price=479.25,
        basis=1.40,
        cash_price_bu=6.19,
        cash_price_mt=243.79,
        basis_change=None,
        cash_price_bu_change=None,
        cash_price_mt_change=None,
        composite_key=f"{location}|{commodity_name}|{delivery_end}|{futures_month}",
        is_canonical=is_canonical,
        canonical_rank=None,
        canonical_reason=None,
    )


def test_summarize_duplicate_candidates_groups_by_company_and_market_key() -> None:
    glg_id = uuid.uuid4()
    rows = [
        _build_row(source_name="GLG", company_id=glg_id, is_canonical=True),
        _build_row(source_name="Ontario Daily File", company_id=glg_id),
        _build_row(source_name="GLG", company_id=glg_id, location="Prescott Soybeans", commodity_name="Soybeans"),
        _build_row(source_name="Ontario Daily File", company_id=glg_id, location="Prescott Soybeans", commodity_name="Soybeans"),
        _build_row(source_name="Snobelen", company_id=uuid.uuid4(), location="Chatham", commodity_name="Corn"),
    ]

    summary = summarize_duplicate_candidates(rows, company_names={glg_id: "GLG"})

    assert len(summary) == 1
    assert summary[0]["company_name"] == "GLG"
    assert summary[0]["duplicate_market_keys"] == 2
    assert summary[0]["candidate_rows"] == 4
    assert summary[0]["alternate_rows"] == 2
    assert summary[0]["canonical_rows"] == 1
    assert summary[0]["sample_markets"] == [
        "Blenheim | Corn | May 2026 | Jul 2026",
        "Prescott | Soybeans | May 2026 | Jul 2026",
    ]


def test_summarize_duplicate_candidates_falls_back_to_source_name_without_company_mapping() -> None:
    rows = [
        _build_row(source_name="Ontario Daily File", company_id=None, is_canonical=True),
        _build_row(source_name="Ontario Daily File", company_id=None),
    ]

    summary = summarize_duplicate_candidates(rows)

    assert len(summary) == 1
    assert summary[0]["company_id"] is None
    assert summary[0]["company_name"] == "Ontario Cash Bids"
    assert summary[0]["duplicate_market_keys"] == 1


def test_source_file_path_for_reprocess_prefers_snapshot_payload() -> None:
    path = _source_file_path_for_reprocess(
        {"source_file_path": r"P:\Adam\Code\TestingGrainBidder\TestOutput\Ontario_CashBids_latest.xlsx"},
        r"C:\fallback\latest.xlsx",
    )
    assert path == r"P:\Adam\Code\TestingGrainBidder\TestOutput\Ontario_CashBids_latest.xlsx"


def test_source_file_path_for_reprocess_falls_back_to_source_url() -> None:
    path = _source_file_path_for_reprocess({}, r"C:\Users\Scaleuser\Documents\Code\GrainBids\latest.xlsx")
    assert path == r"C:\Users\Scaleuser\Documents\Code\GrainBids\latest.xlsx"


def test_source_file_path_for_reprocess_prefers_explicit_override() -> None:
    path = _source_file_path_for_reprocess(
        {"source_file_path": r"P:\Adam\Code\TestingGrainBidder\TestOutput\Ontario_CashBids_latest.xlsx"},
        r"C:\fallback\latest.xlsx",
        source_file_path_override=r"C:\Users\Scaleuser\Documents\Data\Ontario_CashBids_latest.xlsx",
    )
    assert path == r"C:\Users\Scaleuser\Documents\Data\Ontario_CashBids_latest.xlsx"
