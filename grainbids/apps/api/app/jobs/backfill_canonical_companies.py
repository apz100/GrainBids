from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models.company import Company
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_key, canonical_source_name


@dataclass
class BackfillStats:
    scanned_rows: int = 0
    updated_rows: int = 0
    updated_source_name: int = 0
    updated_company_ref: int = 0
    created_companies: int = 0


def _resolve_company_id(
    db: Session,
    *,
    org_id: uuid.UUID,
    canonical_company_name: str,
    cache: dict[tuple[uuid.UUID, str], uuid.UUID],
    stats: BackfillStats,
    dry_run: bool,
) -> uuid.UUID:
    key = canonical_key(canonical_company_name)
    if key is None:
        raise ValueError("canonical_company_name cannot be blank")

    cache_key = (org_id, key)
    cached = cache.get(cache_key)
    if cached:
        return cached

    company = db.execute(
        select(Company).where(
            Company.org_id == org_id,
            Company.canonical_key == key,
        )
    ).scalar_one_or_none()

    if company is None:
        if dry_run:
            simulated_id = uuid.uuid4()
            cache[cache_key] = simulated_id
            stats.created_companies += 1
            return simulated_id
        company = Company(org_id=org_id, name=canonical_company_name, canonical_key=key)
        db.add(company)
        db.flush()
        stats.created_companies += 1
    elif company.name != canonical_company_name:
        company.name = canonical_company_name

    cache[cache_key] = company.id
    return company.id


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
            canonical_company = canonical_source_name(price_row.source_name)
            if not canonical_company:
                continue

            company_id = _resolve_company_id(
                session,
                org_id=source_row.org_id,
                canonical_company_name=canonical_company,
                cache=cache,
                stats=stats,
                dry_run=dry_run,
            )

            changed = False
            if price_row.source_name != canonical_company:
                price_row.source_name = canonical_company
                stats.updated_source_name += 1
                changed = True
            if price_row.company_id != company_id:
                price_row.company_id = company_id
                stats.updated_company_ref += 1
                changed = True
            if changed:
                stats.updated_rows += 1

            if index % max(1, batch_size) == 0 and not dry_run:
                session.commit()

        if dry_run:
            session.rollback()
        else:
            # also normalize existing company display names
            company_query = select(Company)
            if org_id is not None:
                company_query = company_query.where(Company.org_id == org_id)
            for company in session.execute(company_query).scalars().all():
                canonical = canonical_source_name(company.name)
                key = canonical_key(canonical)
                if canonical and key:
                    company.name = canonical
                    company.canonical_key = key
            session.commit()

        return stats
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill canonical company names and company IDs.")
    parser.add_argument("--org-id", type=str, default="", help="Optional org UUID to scope the backfill.")
    parser.add_argument("--dry-run", action="store_true", help="Compute stats without persisting updates.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Commit interval for updates.")
    args = parser.parse_args()

    scoped_org = uuid.UUID(args.org_id) if args.org_id else None
    stats = run_backfill(org_id=scoped_org, dry_run=args.dry_run, batch_size=args.batch_size)
    print(
        f"scanned={stats.scanned_rows} updated={stats.updated_rows} "
        f"source_name_updates={stats.updated_source_name} company_ref_updates={stats.updated_company_ref} "
        f"created_companies={stats.created_companies} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
