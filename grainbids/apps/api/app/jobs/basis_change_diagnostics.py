from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.organization import Organization
from app.services.basis_change_diagnostics import build_basis_change_diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect strict-vs-carried basis-change state for the latest snapshot.")
    parser.add_argument("--org-id", type=str, default="", help="Organization UUID override.")
    parser.add_argument("--source-id", type=str, default="", help="Optional source UUID filter.")
    parser.add_argument("--limit", type=int, default=25, help="Max row samples to print.")
    parser.add_argument("--min-snapshot-rows", type=int, default=25, help="Prefer latest snapshot with at least this many rows.")
    args = parser.parse_args()

    session = get_sessionmaker()()
    try:
        org_id = _resolve_org_id(session, args.org_id)
        source_id = uuid.UUID(args.source_id) if args.source_id else None
        payload = build_basis_change_diagnostics(
            session,
            org_id=org_id,
            source_id=source_id,
            limit=max(1, args.limit),
            min_snapshot_rows=max(1, args.min_snapshot_rows),
        )
        _print_payload(payload)
        return 0
    finally:
        session.close()


def _resolve_org_id(session, override: str) -> uuid.UUID:
    if override:
        return uuid.UUID(override)
    org = session.execute(select(Organization).order_by(Organization.created_at.asc()).limit(1)).scalar_one_or_none()
    if org is None:
        raise RuntimeError("No organization exists. Provide --org-id after creating one.")
    return org.id


def _print_payload(payload: dict[str, object]) -> None:
    latest_snapshot = payload.get("latest_snapshot")
    if not isinstance(latest_snapshot, dict):
        print("latest_snapshot none")
        return

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    print(
        "latest_snapshot "
        f"id={latest_snapshot.get('id')} source={latest_snapshot.get('source_name')} "
        f"captured_at={latest_snapshot.get('captured_at')} rows={latest_snapshot.get('row_count')}"
    )
    print(
        "summary "
        f"strict_non_zero={summary.get('strict_non_zero_count')} "
        f"carried_non_zero={summary.get('carried_non_zero_count')} "
        f"carried_without_strict={summary.get('carried_without_strict_count')} "
        f"strict_without_carried={summary.get('strict_without_carried_count')} "
        f"value_mismatch={summary.get('strict_vs_carried_value_mismatch_count')} "
        f"stale_non_zero={summary.get('stale_non_zero_carried_count')}"
    )

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        print("rows none")
        return

    for row in rows:
        if not isinstance(row, dict):
            continue
        print(
            "row "
            f"location={row.get('location')} commodity={row.get('commodity_name')} "
            f"delivery={row.get('delivery_label')} futures={row.get('futures_month')} "
            f"basis={row.get('basis')} carried={row.get('basis_change')} strict={row.get('basis_change_strict')} "
            f"diff={row.get('basis_change_diff')} stale={row.get('is_stale_non_zero')} "
            f"last_changed_at={row.get('basis_last_changed_at')} age_hours={row.get('basis_last_changed_age_hours')}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
