from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.company import Company
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.canonical_resolver import _market_key_from_row, resolve_canonical_rows_for_market_keys
from app.services.market_canonicalization import canonical_key, canonical_source_name
from app.services.upload_csv import _source_creates_company_identity


_SOURCE_LOOKUP_ALIASES: dict[str, tuple[str, ...]] = {
    "great lakes grain": ("glg", "g.l.g.", "agris", "agris co-operative", "agris cooperative", "central ontario fs"),
    "the andersons": ("andersons", "thompsons", "thompsons ltd", "thompsons limited"),
    "london agricultural commodities": ("lac", "london ag commodities"),
    "hensall co-operative": ("hensall", "hensall hdc", "hdc", "hensall co-op", "hensall cooperative"),
    "snobelen farms": ("snobelen",),
    "port of prescott": ("port of prescott grain terminal",),
    "agricharts": ("agricharts",),
    "wanstead": ("wanstead",),
}


@dataclass
class BackfillStats:
    scanned_rows: int = 0
    updated_rows: int = 0
    reassigned_row_company_refs: int = 0
    cleared_row_company_refs: int = 0
    scanned_locations: int = 0
    updated_locations: int = 0
    reassigned_location_company_refs: int = 0
    cleared_location_company_refs: int = 0
    ambiguous_locations: int = 0
    impacted_market_keys: int = 0
    canonical_rows: int = 0
    canonical_updates: int = 0


def _company_lookup_maps(
    session,
    *,
    org_id: uuid.UUID,
) -> tuple[dict[uuid.UUID, str], dict[str, uuid.UUID]]:
    rows = session.execute(select(Company.id, Company.name).where(Company.org_id == org_id)).all()
    company_name_map: dict[uuid.UUID, str] = {}
    trusted_company_lookup: dict[str, uuid.UUID] = {}
    for company_id, company_name in rows:
        if company_id is None or not company_name:
            continue
        company_name_map[company_id] = company_name
        if not _source_creates_company_identity(company_name):
            continue
        for key in _source_lookup_keys(company_name):
            trusted_company_lookup[key] = company_id
    return company_name_map, trusted_company_lookup


def _source_lookup_keys(source_name: str | None) -> tuple[str, ...]:
    keys: list[str] = []
    for candidate in (source_name, canonical_source_name(source_name)):
        key = canonical_key(candidate)
        if key and key not in keys:
            keys.append(key)
        if candidate is None:
            continue
        alias_candidates = _SOURCE_LOOKUP_ALIASES.get(candidate.casefold(), ())
        for alias in alias_candidates:
            alias_key = canonical_key(alias)
            if alias_key and alias_key not in keys:
                keys.append(alias_key)
    return tuple(keys)


def _is_trusted_company_id(
    company_id: uuid.UUID | None,
    *,
    company_name_map: dict[uuid.UUID, str],
) -> bool:
    if company_id is None:
        return False
    company_name = company_name_map.get(company_id)
    return _source_creates_company_identity(company_name)


def _infer_location_company_id(
    *,
    current_company_id: uuid.UUID | None,
    candidate_company_ids: set[uuid.UUID],
    company_name_map: dict[uuid.UUID, str],
) -> tuple[uuid.UUID | None, bool]:
    current_trusted = current_company_id if _is_trusted_company_id(current_company_id, company_name_map=company_name_map) else None
    trusted_candidates = {company_id for company_id in candidate_company_ids if _is_trusted_company_id(company_id, company_name_map=company_name_map)}
    if current_trusted is not None:
        return current_trusted, len(trusted_candidates) > 1
    if len(trusted_candidates) == 1:
        return next(iter(trusted_candidates)), False
    return None, len(trusted_candidates) > 1


def _desired_company_id_for_row(
    *,
    source_name: str | None,
    current_company_id: uuid.UUID | None,
    trusted_location_company_id: uuid.UUID | None,
    company_name_map: dict[uuid.UUID, str],
    trusted_company_lookup: dict[str, uuid.UUID],
) -> uuid.UUID | None:
    if _source_creates_company_identity(source_name):
        source_keys = _source_lookup_keys(source_name)
        if _is_trusted_company_id(current_company_id, company_name_map=company_name_map):
            current_company_name = company_name_map.get(current_company_id)
            current_key = canonical_key(canonical_source_name(current_company_name))
            if current_key is not None and current_key in source_keys:
                return current_company_id
        for source_key in source_keys:
            trusted_company_id = trusted_company_lookup.get(source_key)
            if trusted_company_id is not None:
                return trusted_company_id
        return None
    return trusted_location_company_id


def run_backfill(
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None,
    dry_run: bool,
) -> BackfillStats:
    session = get_sessionmaker()()
    stats = BackfillStats()

    try:
        target_query = (
            select(NormalizedPrice, Source)
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .where(Source.org_id == org_id)
            .order_by(NormalizedPrice.created_at.asc())
        )
        if source_id is not None:
            target_query = target_query.where(Source.id == source_id)

        target_rows = session.execute(target_query).all()
        if not target_rows:
            if dry_run:
                session.rollback()
            return stats

        company_name_map, trusted_company_lookup = _company_lookup_maps(session, org_id=org_id)
        target_location_ids = {price_row.location_id for price_row, _source_row in target_rows if price_row.location_id is not None}

        trusted_location_company_by_id: dict[uuid.UUID, uuid.UUID | None] = {}
        if target_location_ids:
            locations = session.execute(
                select(Location).where(
                    Location.org_id == org_id,
                    Location.id.in_(target_location_ids),
                )
            ).scalars().all()
            location_candidates: dict[uuid.UUID, set[uuid.UUID]] = {location.id: set() for location in locations}
            for location in locations:
                if location.company_id is not None:
                    location_candidates[location.id].add(location.company_id)

            candidate_rows = session.execute(
                select(NormalizedPrice.location_id, NormalizedPrice.company_id, NormalizedPrice.source_name)
                .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
                .join(Source, Source.id == PriceSnapshot.source_id)
                .where(
                    Source.org_id == org_id,
                    NormalizedPrice.location_id.in_(target_location_ids),
                )
            ).all()
            for location_id, company_id, source_name in candidate_rows:
                if location_id is None or company_id is None:
                    continue
                if not _source_creates_company_identity(source_name):
                    continue
                if not _is_trusted_company_id(company_id, company_name_map=company_name_map):
                    continue
                location_candidates.setdefault(location_id, set()).add(company_id)

            for location in locations:
                stats.scanned_locations += 1
                inferred_company_id, is_ambiguous = _infer_location_company_id(
                    current_company_id=location.company_id,
                    candidate_company_ids=location_candidates.get(location.id, set()),
                    company_name_map=company_name_map,
                )
                if is_ambiguous:
                    stats.ambiguous_locations += 1
                trusted_location_company_by_id[location.id] = inferred_company_id
                if location.company_id == inferred_company_id:
                    continue
                if inferred_company_id is None and location.company_id is None:
                    continue
                location.company_id = inferred_company_id
                stats.updated_locations += 1
                if inferred_company_id is None:
                    stats.cleared_location_company_refs += 1
                else:
                    stats.reassigned_location_company_refs += 1

        impacted_market_keys: set[tuple[str, str, str, str, str]] = set()
        for price_row, _source_row in target_rows:
            stats.scanned_rows += 1
            previous_key = _market_key_from_row(price_row)
            desired_company_id = _desired_company_id_for_row(
                source_name=price_row.source_name,
                current_company_id=price_row.company_id,
                trusted_location_company_id=trusted_location_company_by_id.get(price_row.location_id) if price_row.location_id else None,
                company_name_map=company_name_map,
                trusted_company_lookup=trusted_company_lookup,
            )
            if price_row.company_id == desired_company_id:
                continue
            price_row.company_id = desired_company_id
            impacted_market_keys.add(previous_key)
            impacted_market_keys.add(_market_key_from_row(price_row))
            stats.updated_rows += 1
            if desired_company_id is None:
                stats.cleared_row_company_refs += 1
            else:
                stats.reassigned_row_company_refs += 1

        stats.impacted_market_keys = len(impacted_market_keys)
        if dry_run:
            session.rollback()
            return stats

        session.flush()
        if impacted_market_keys:
            canonical_result = resolve_canonical_rows_for_market_keys(
                session,
                org_id=org_id,
                market_keys=impacted_market_keys,
            )
            stats.canonical_rows = int(canonical_result.get("canonical_rows", 0))
            stats.canonical_updates = int(canonical_result.get("updated_rows", 0))
        session.commit()
        return stats
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill source-derived company identities for existing normalized rows.")
    parser.add_argument("--org-id", required=True, help="Org UUID to scope the backfill.")
    parser.add_argument("--source-id", default="", help="Optional source UUID to limit which normalized rows are updated.")
    parser.add_argument("--dry-run", action="store_true", help="Compute stats without persisting updates.")
    args = parser.parse_args()

    stats = run_backfill(
        org_id=uuid.UUID(args.org_id),
        source_id=uuid.UUID(args.source_id) if args.source_id else None,
        dry_run=args.dry_run,
    )
    print(
        f"scanned_rows={stats.scanned_rows} updated_rows={stats.updated_rows} "
        f"reassigned_row_company_refs={stats.reassigned_row_company_refs} "
        f"cleared_row_company_refs={stats.cleared_row_company_refs} "
        f"scanned_locations={stats.scanned_locations} updated_locations={stats.updated_locations} "
        f"reassigned_location_company_refs={stats.reassigned_location_company_refs} "
        f"cleared_location_company_refs={stats.cleared_location_company_refs} "
        f"ambiguous_locations={stats.ambiguous_locations} "
        f"impacted_market_keys={stats.impacted_market_keys} "
        f"canonical_rows={stats.canonical_rows} canonical_updates={stats.canonical_updates} "
        f"dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
