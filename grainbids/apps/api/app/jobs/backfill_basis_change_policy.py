from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db.session import get_sessionmaker
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.price_comparison import apply_historical_changes


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
    session = session_factory()
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

        snapshots = session.execute(snapshot_query).all()
        if max_snapshots is not None and max_snapshots > 0 and len(snapshots) > max_snapshots:
            snapshots = snapshots[-max_snapshots:]
        commit_batch_size = max(1, int(commit_every))
        for idx, (snapshot_id, captured_at, snapshot_org_id) in enumerate(snapshots, start=1):
            stats.snapshots_scanned += 1
            worker = session_factory()
            try:
                rows = worker.execute(
                    select(NormalizedPrice)
                    .where(NormalizedPrice.snapshot_id == snapshot_id)
                    .with_for_update(skip_locked=True)
                ).scalars().all()
                if not rows:
                    if dry_run:
                        worker.rollback()
                    else:
                        worker.commit()
                    continue
                stats.rows_scanned += len(rows)

                previous_state = {row.id: _state(row) for row in rows}
                apply_historical_changes(
                    worker,
                    normalized_rows=rows,
                    captured_at=captured_at,
                    org_id=snapshot_org_id,
                )
                for row in rows:
                    if _state(row) != previous_state[row.id]:
                        stats.rows_updated += 1

                try:
                    worker.flush()
                except OperationalError as exc:
                    worker.rollback()
                    print(f"warning snapshot={idx}/{len(snapshots)} skipped_due_to_lock_or_timeout error={exc.__class__.__name__}")
                    continue
                if dry_run:
                    worker.rollback()
                else:
                    worker.commit()
                    if idx % commit_batch_size == 0:
                        print(f"commit snapshot={idx}/{len(snapshots)}")
            finally:
                worker.close()
            if idx == 1 or idx % 25 == 0:
                print(
                    f"progress snapshot={idx}/{len(snapshots)} rows_scanned={stats.rows_scanned} "
                    f"rows_updated={stats.rows_updated}"
                )
        return stats
    finally:
        session.close()


def _state(row: NormalizedPrice) -> tuple[object, object, object, object, object]:
    return (
        row.basis_change,
        row.basis_change_strict,
        row.basis_last_changed_at,
        row.cash_price_bu_change,
        row.cash_price_mt_change,
    )


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
