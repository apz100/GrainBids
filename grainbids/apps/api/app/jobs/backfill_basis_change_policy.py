from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import uuid

from sqlalchemy import select, text

from app.db.session import get_sessionmaker
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.price_comparison import (
    calculate_basis_change_policy,
    calculate_price_changes,
)


@dataclass(frozen=True)
class SnapshotInfo:
    snapshot_id: uuid.UUID
    captured_at: datetime
    org_id: uuid.UUID | None


@dataclass(frozen=True)
class HistoricalRow:
    row_id: uuid.UUID
    snapshot_id: uuid.UUID
    captured_at: datetime
    composite_key: str
    basis: object
    cash_price_bu: object
    cash_price_mt: object
    basis_change: object
    basis_change_strict: object
    basis_last_changed_at: datetime | None
    cash_price_bu_change: object
    cash_price_mt_change: object


@dataclass(frozen=True)
class RowState:
    basis: object
    cash_price_bu: object
    cash_price_mt: object
    basis_change: object
    basis_change_strict: object
    basis_last_changed_at: datetime | None
    cash_price_bu_change: object
    cash_price_mt_change: object


@dataclass
class BackfillStats:
    snapshots_scanned: int = 0
    rows_scanned: int = 0
    rows_updated: int = 0


def run_backfill(
    *,
    org_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    days: int,
    max_snapshots: int | None,
    commit_every: int,
    dry_run: bool,
) -> BackfillStats:
    session_factory = get_sessionmaker()
    read_session = session_factory()
    stats = BackfillStats()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))

    try:
        snapshot_query = (
            select(PriceSnapshot.id, PriceSnapshot.captured_at, Source.org_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .where(PriceSnapshot.captured_at >= cutoff)
            .order_by(PriceSnapshot.captured_at.asc(), PriceSnapshot.id.asc())
        )
        if org_id is not None:
            snapshot_query = snapshot_query.where(Source.org_id == org_id)
        if source_id is not None:
            snapshot_query = snapshot_query.where(PriceSnapshot.source_id == source_id)

        snapshots = [
            SnapshotInfo(snapshot_id=snapshot_id, captured_at=captured_at, org_id=snapshot_org_id)
            for snapshot_id, captured_at, snapshot_org_id in read_session.execute(snapshot_query).all()
        ]
        if max_snapshots is not None and max_snapshots > 0 and len(snapshots) > max_snapshots:
            snapshots = snapshots[-max_snapshots:]
        if not snapshots:
            return stats

        snapshot_ids = [snapshot.snapshot_id for snapshot in snapshots]
        row_query = (
            select(
                NormalizedPrice.id,
                NormalizedPrice.snapshot_id,
                PriceSnapshot.captured_at,
                NormalizedPrice.composite_key,
                NormalizedPrice.basis,
                NormalizedPrice.cash_price_bu,
                NormalizedPrice.cash_price_mt,
                NormalizedPrice.basis_change,
                NormalizedPrice.basis_change_strict,
                NormalizedPrice.basis_last_changed_at,
                NormalizedPrice.cash_price_bu_change,
                NormalizedPrice.cash_price_mt_change,
            )
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .where(NormalizedPrice.snapshot_id.in_(snapshot_ids))
            .order_by(
                PriceSnapshot.captured_at.asc(),
                NormalizedPrice.snapshot_id.asc(),
                NormalizedPrice.composite_key.asc(),
                NormalizedPrice.id.asc(),
            )
        )
        if org_id is not None:
            row_query = row_query.join(Source, Source.id == PriceSnapshot.source_id).where(Source.org_id == org_id)
        if source_id is not None:
            row_query = row_query.where(PriceSnapshot.source_id == source_id)

        rows_by_snapshot: dict[uuid.UUID, list[HistoricalRow]] = defaultdict(list)
        for row in read_session.execute(row_query).all():
            rows_by_snapshot[row.snapshot_id].append(
                HistoricalRow(
                    row_id=row.id,
                    snapshot_id=row.snapshot_id,
                    captured_at=row.captured_at,
                    composite_key=row.composite_key,
                    basis=row.basis,
                    cash_price_bu=row.cash_price_bu,
                    cash_price_mt=row.cash_price_mt,
                    basis_change=row.basis_change,
                    basis_change_strict=row.basis_change_strict,
                    basis_last_changed_at=row.basis_last_changed_at,
                    cash_price_bu_change=row.cash_price_bu_change,
                    cash_price_mt_change=row.cash_price_mt_change,
                )
            )

        commit_batch_size = max(1, int(commit_every))
        updates_stmt = text(
            """
            UPDATE normalized_prices
            SET basis_change = :basis_change,
                basis_change_strict = :basis_change_strict,
                basis_last_changed_at = :basis_last_changed_at,
                cash_price_bu_change = :cash_price_bu_change,
                cash_price_mt_change = :cash_price_mt_change
            WHERE id = :row_id
            """
        )

        current_day: date | None = None
        last_weekday_state_by_key: dict[str, RowState] = {}
        day_prior_state_by_key: dict[str, RowState] = {}
        pending_updates: list[dict[str, object]] = []
        write_session = session_factory()

        try:
            for idx, snapshot in enumerate(snapshots, start=1):
                stats.snapshots_scanned += 1
                snapshot_day = snapshot.captured_at.date()
                if snapshot_day != current_day:
                    current_day = snapshot_day
                    day_prior_state_by_key = dict(last_weekday_state_by_key)

                snapshot_rows = rows_by_snapshot.get(snapshot.snapshot_id, [])
                if not snapshot_rows:
                    if not dry_run:
                        write_session.commit()
                    continue

                stats.rows_scanned += len(snapshot_rows)
                changed_rows_for_snapshot = 0

                for row in snapshot_rows:
                    prior_day_state = last_weekday_state_by_key.get(row.composite_key)
                    prior_run_state = day_prior_state_by_key.get(row.composite_key)
                    changes = calculate_price_changes(
                        basis=row.basis,
                        cash_price_bu=row.cash_price_bu,
                        cash_price_mt=row.cash_price_mt,
                        prior_basis=prior_day_state.basis if prior_day_state else None,
                        prior_cash_price_bu=prior_day_state.cash_price_bu if prior_day_state else None,
                        prior_cash_price_mt=prior_day_state.cash_price_mt if prior_day_state else None,
                    )
                    basis_policy = calculate_basis_change_policy(
                        basis=row.basis,
                        captured_at=snapshot.captured_at,
                        prior_day_basis=prior_day_state.basis if prior_day_state else None,
                        prior_run_basis=prior_run_state.basis if prior_run_state else None,
                        prior_user_basis_change=prior_run_state.basis_change if prior_run_state else None,
                        prior_basis_last_changed_at=prior_run_state.basis_last_changed_at if prior_run_state else None,
                    )

                    desired_state = RowState(
                        basis=row.basis,
                        cash_price_bu=row.cash_price_bu,
                        cash_price_mt=row.cash_price_mt,
                        basis_change=basis_policy.basis_change,
                        basis_change_strict=basis_policy.basis_change_strict,
                        basis_last_changed_at=basis_policy.basis_last_changed_at,
                        cash_price_bu_change=changes.cash_price_bu_change,
                        cash_price_mt_change=changes.cash_price_mt_change,
                    )
                    current_state = RowState(
                        basis=row.basis,
                        cash_price_bu=row.cash_price_bu,
                        cash_price_mt=row.cash_price_mt,
                        basis_change=row.basis_change,
                        basis_change_strict=row.basis_change_strict,
                        basis_last_changed_at=row.basis_last_changed_at,
                        cash_price_bu_change=row.cash_price_bu_change,
                        cash_price_mt_change=row.cash_price_mt_change,
                    )

                    day_prior_state_by_key[row.composite_key] = desired_state

                    if desired_state != current_state:
                        changed_rows_for_snapshot += 1
                        stats.rows_updated += 1
                        pending_updates.append(
                            {
                                "row_id": row.row_id,
                                "basis_change": basis_policy.basis_change,
                                "basis_change_strict": basis_policy.basis_change_strict,
                                "basis_last_changed_at": basis_policy.basis_last_changed_at,
                                "cash_price_bu_change": changes.cash_price_bu_change,
                                "cash_price_mt_change": changes.cash_price_mt_change,
                            }
                        )

                if snapshot_day.weekday() < 5:
                    last_weekday_state_by_key = dict(day_prior_state_by_key)

                if dry_run:
                    pending_updates.clear()
                elif pending_updates:
                    write_session.execute(updates_stmt, pending_updates)
                    write_session.commit()
                    pending_updates.clear()

                if idx == 1 or idx % 25 == 0:
                    print(
                        f"progress snapshot={idx}/{len(snapshots)} rows_scanned={stats.rows_scanned} "
                        f"rows_updated={stats.rows_updated}"
                    )

            return stats
        finally:
            write_session.close()
    finally:
        read_session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill GrainBids basis-change carry policy fields.")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30).")
    parser.add_argument("--org-id", default="", help="Optional org UUID scope. When omitted, all orgs are included.")
    parser.add_argument("--source-id", default="", help="Optional source UUID scope.")
    parser.add_argument(
        "--max-snapshots",
        type=int,
        default=0,
        help="Optional cap on number of most-recent snapshots to process (0 means no cap).",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=25,
        help="Commit every N snapshots in non-dry-run mode (default: 25).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute updates without persisting changes.")
    args = parser.parse_args()

    stats = run_backfill(
        org_id=uuid.UUID(args.org_id) if args.org_id else None,
        source_id=uuid.UUID(args.source_id) if args.source_id else None,
        days=args.days,
        max_snapshots=args.max_snapshots if args.max_snapshots > 0 else None,
        commit_every=max(1, int(args.commit_every)),
        dry_run=args.dry_run,
    )
    print(
        f"snapshots_scanned={stats.snapshots_scanned} rows_scanned={stats.rows_scanned} "
        f"rows_updated={stats.rows_updated} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
