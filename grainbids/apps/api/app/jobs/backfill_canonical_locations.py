from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_location_name, canonical_key, normalize_text


@dataclass
class BackfillStats:
    scanned_rows: int = 0
    updated_rows: int = 0
    created_locations: int = 0
    updated_location_text: int = 0
    updated_location_ref: int = 0


def _resolve_location_id(
    db: Session,
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID | None,
    source_region: str | None,
    canonical_location: str,
    cache: dict[tuple[uuid.UUID, str], uuid.UUID],
    stats: BackfillStats,
    dry_run: bool,
) -> uuid.UUID:
    key = canonical_key(canonical_location)
    if key is None:
        raise ValueError("canonical_location cannot be blank")

    cache_key = (org_id, key)
    cached = cache.get(cache_key)
    if cached:
        return cached

    row = db.execute(
        select(Location).where(
            Location.org_id == org_id,
            Location.canonical_key == key,
        )
    ).scalar_one_or_none()

    if row is None:
        if dry_run:
            simulated = uuid.uuid4()
            cache[cache_key] = simulated
            stats.created_locations += 1
            return simulated
        row = Location(
            org_id=org_id,
            company_id=company_id,
            name=canonical_location,
            canonical_key=key,
            region=normalize_text(source_region),
        )
        db.add(row)
        db.flush()
        stats.created_locations += 1
    else:
        if row.company_id is None and company_id is not None:
            row.company_id = company_id
        if row.region is None and normalize_text(source_region):
            row.region = normalize_text(source_region)

    cache[cache_key] = row.id
    return row.id


def run_backfill(*, org_id: uuid.UUID | None, dry_run: bool, batch_size: int) -> BackfillStats:
    session = get_sessionmaker()()
    stats = BackfillStats()
    cache: dict[tuple[uuid.UUID, str], uuid.UUID] = {}

    try:
        query = (
            select(NormalizedPrice, Source)
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .order_by(NormalizedPrice.created_at.asc())
        )
        if org_id is not None:
            query = query.where(Source.org_id == org_id)

        rows = session.execute(query).all()
        for index, (price_row, source_row) in enumerate(rows, start=1):
            stats.scanned_rows += 1

            canonical_location = canonical_location_name(price_row.location)
            if canonical_location is None:
                continue

            location_id = _resolve_location_id(
                session,
                org_id=source_row.org_id,
                company_id=price_row.company_id,
                source_region=source_row.region,
                canonical_location=canonical_location,
                cache=cache,
                stats=stats,
                dry_run=dry_run,
            )

            changed = False
            if price_row.location != canonical_location:
                price_row.location = canonical_location
                stats.updated_location_text += 1
                changed = True
            if price_row.location_id != location_id:
                price_row.location_id = location_id
                stats.updated_location_ref += 1
                changed = True

            if changed:
                stats.updated_rows += 1

            if index % max(1, batch_size) == 0 and not dry_run:
                session.commit()

        if dry_run:
            session.rollback()
        else:
            session.commit()

        return stats
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill canonical location names and location IDs.")
    parser.add_argument("--org-id", type=str, default="", help="Optional org UUID to scope the backfill.")
    parser.add_argument("--dry-run", action="store_true", help="Compute stats without persisting updates.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Commit interval for updates.")
    args = parser.parse_args()

    org_id = uuid.UUID(args.org_id) if args.org_id else None
    stats = run_backfill(org_id=org_id, dry_run=args.dry_run, batch_size=args.batch_size)
    print(
        f"scanned={stats.scanned_rows} updated={stats.updated_rows} "
        f"text_updates={stats.updated_location_text} ref_updates={stats.updated_location_ref} "
        f"created_locations={stats.created_locations} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
