from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from app.models.normalized_price import NormalizedPrice
from app.services.basis_change_diagnostics import summarize_basis_change_rows


def _build_row(
    *,
    location: str,
    basis_change_strict: float | None,
    basis_change: float | None,
    basis_last_changed_at: datetime | None = None,
) -> NormalizedPrice:
    return NormalizedPrice(
        id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        company_id=None,
        location_id=None,
        location=location,
        commodity_name="Corn",
        source_name="Ontario Daily File",
        delivery_start=None,
        delivery_end="May 2026",
        delivery_label="May 2026",
        futures_month="Jul 2026",
        futures_price=479.25,
        basis=1.40,
        cash_price_bu=6.19,
        cash_price_mt=243.79,
        basis_change=basis_change,
        basis_change_strict=basis_change_strict,
        basis_last_changed_at=basis_last_changed_at,
        cash_price_bu_change=0.0,
        cash_price_mt_change=0.0,
        composite_key=f"{location}|Corn|May 2026|Jul 2026",
        is_canonical=True,
        canonical_rank=1,
        canonical_reason="test",
    )


def test_summarize_basis_change_rows_counts_deltas_and_stale_rows() -> None:
    captured_at = datetime(2026, 5, 29, 14, 0, tzinfo=timezone.utc)
    rows = [
        _build_row(
            location="CarriedTown",
            basis_change_strict=0.0,
            basis_change=0.10,
            basis_last_changed_at=captured_at - timedelta(hours=4),
        ),
        _build_row(
            location="StrictTown",
            basis_change_strict=-0.05,
            basis_change=0.0,
            basis_last_changed_at=None,
        ),
        _build_row(
            location="MismatchTown",
            basis_change_strict=0.04,
            basis_change=0.02,
            basis_last_changed_at=None,
        ),
        _build_row(
            location="StaleTown",
            basis_change_strict=0.0,
            basis_change=0.03,
            basis_last_changed_at=captured_at - timedelta(hours=30),
        ),
    ]

    summary, sample_rows = summarize_basis_change_rows(rows, captured_at=captured_at, limit=10)

    assert summary["row_count"] == 4
    assert summary["strict_non_zero_count"] == 2
    assert summary["carried_non_zero_count"] == 3
    assert summary["carried_without_strict_count"] == 2
    assert summary["strict_without_carried_count"] == 1
    assert summary["strict_vs_carried_value_mismatch_count"] == 1
    assert summary["stale_non_zero_carried_count"] == 1
    assert summary["rows_with_basis_last_changed_at"] == 2

    assert len(sample_rows) == 4
    assert sample_rows[0]["location"] == "StaleTown"
    assert sample_rows[0]["is_stale_non_zero"] is True


def test_summarize_basis_change_rows_returns_no_samples_when_values_match() -> None:
    captured_at = datetime(2026, 5, 29, 14, 0, tzinfo=timezone.utc)
    rows = [
        _build_row(
            location="StableTown",
            basis_change_strict=0.0,
            basis_change=0.0,
            basis_last_changed_at=None,
        ),
        _build_row(
            location="MoveTown",
            basis_change_strict=0.06,
            basis_change=0.06,
            basis_last_changed_at=captured_at - timedelta(hours=1),
        ),
    ]

    summary, sample_rows = summarize_basis_change_rows(rows, captured_at=captured_at, limit=10)

    assert summary["row_count"] == 2
    assert summary["strict_non_zero_count"] == 1
    assert summary["carried_non_zero_count"] == 1
    assert summary["carried_without_strict_count"] == 0
    assert summary["strict_without_carried_count"] == 0
    assert summary["strict_vs_carried_value_mismatch_count"] == 0
    assert summary["stale_non_zero_carried_count"] == 0
    assert summary["rows_with_basis_last_changed_at"] == 1
    assert sample_rows == []
