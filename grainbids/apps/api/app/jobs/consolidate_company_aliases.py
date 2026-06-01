from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.company import Company
from app.models.company_source_priority import CompanySourcePriority
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.services.market_canonicalization import canonical_key, canonical_source_name, normalize_text


CANONICAL_COMPANY_ALIASES: tuple[tuple[str, str], ...] = (
    ("thompsons", "The Andersons"),
    ("thompsons ltd", "The Andersons"),
    ("thompsons limited", "The Andersons"),
    ("andersons", "The Andersons"),
    ("the andersons", "The Andersons"),
    ("glg", "Great Lakes Grain"),
    ("great lakes grain", "Great Lakes Grain"),
    ("agris", "Great Lakes Grain"),
    ("agris co-operative", "Great Lakes Grain"),
    ("agris cooperative", "Great Lakes Grain"),
    ("central ontario fs", "Great Lakes Grain"),
    ("lac", "London Agricultural Commodities"),
    ("london ag commodities", "London Agricultural Commodities"),
    ("london agricultural commodities", "London Agricultural Commodities"),
    ("windsor crusher", "ADM"),
    ("hensall", "Hensall Co-operative"),
    ("hensall hdc", "Hensall Co-operative"),
    ("hensall co-op", "Hensall Co-operative"),
    ("hensall cooperative", "Hensall Co-operative"),
    ("hensall co-op / hdc", "Hensall Co-operative"),
    ("snobelen", "Snobelen Farms"),
    ("snobelen farms", "Snobelen Farms"),
    ("ganaraska", "Ganaraska Grains"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate company aliases to canonical company identities.")
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    args = parser.parse_args()

    org_id = uuid.UUID(args.org_id)
    db = get_sessionmaker()()
    try:
        summary = consolidate_company_aliases(db, org_id=org_id)
        print(
            "summary merged_companies={merged_companies} normalized_prices_company_id_updates={normalized_prices_company_id_updates} "
            "locations_company_id_updates={locations_company_id_updates} priority_rows_moved={priority_rows_moved} "
            "priority_rows_merged={priority_rows_merged} normalized_price_company_name_updates={normalized_price_company_name_updates} "
            "mapping_company_name_updates={mapping_company_name_updates}".format(**summary)
        )
        return 0
    finally:
        db.close()


def consolidate_company_aliases(db, *, org_id: uuid.UUID) -> dict[str, int]:
    merged_companies = 0
    normalized_prices_company_id_updates = 0
    locations_company_id_updates = 0
    priority_rows_moved = 0
    priority_rows_merged = 0
    normalized_price_company_name_updates = 0
    mapping_company_name_updates = 0

    for alias_name, target_name in CANONICAL_COMPANY_ALIASES:
        target = _get_or_create_company(db, org_id=org_id, company_name=target_name)
        if target is None:
            continue

        alias_key = canonical_key(alias_name)
        if alias_key is None:
            continue
        alias_rows = db.execute(
            select(Company)
            .where(Company.org_id == org_id)
            .where(Company.canonical_key == alias_key)
            .where(Company.id != target.id)
        ).scalars().all()

        for alias_company in alias_rows:
            normalized_prices_company_id_updates += _bulk_update_company_fk(
                db,
                model=NormalizedPrice,
                company_field_name="company_id",
                source_company_id=alias_company.id,
                target_company_id=target.id,
            )
            locations_company_id_updates += _bulk_update_company_fk(
                db,
                model=Location,
                company_field_name="company_id",
                source_company_id=alias_company.id,
                target_company_id=target.id,
            )
            moved, merged = _merge_company_source_priorities(
                db,
                org_id=org_id,
                source_company_id=alias_company.id,
                target_company_id=target.id,
            )
            priority_rows_moved += moved
            priority_rows_merged += merged
            db.delete(alias_company)
            merged_companies += 1

    db.commit()

    return {
        "merged_companies": merged_companies,
        "normalized_prices_company_id_updates": normalized_prices_company_id_updates,
        "locations_company_id_updates": locations_company_id_updates,
        "priority_rows_moved": priority_rows_moved,
        "priority_rows_merged": priority_rows_merged,
        "normalized_price_company_name_updates": normalized_price_company_name_updates,
        "mapping_company_name_updates": mapping_company_name_updates,
    }


def _get_or_create_company(db, *, org_id: uuid.UUID, company_name: str) -> Company | None:
    normalized_name = canonical_source_name(company_name) or normalize_text(company_name)
    canonical_company_key = canonical_key(normalized_name)
    if normalized_name is None or canonical_company_key is None:
        return None

    row = db.execute(
        select(Company).where(
            Company.org_id == org_id,
            Company.canonical_key == canonical_company_key,
        )
    ).scalar_one_or_none()
    if row is not None:
        if row.name != normalized_name:
            row.name = normalized_name
        return row

    created = Company(
        org_id=org_id,
        name=normalized_name,
        canonical_key=canonical_company_key,
    )
    db.add(created)
    db.flush()
    return created


def _bulk_update_company_fk(
    db,
    *,
    model,
    company_field_name: str,
    source_company_id: uuid.UUID,
    target_company_id: uuid.UUID,
) -> int:
    column = getattr(model, company_field_name)
    rows = db.execute(
        select(model).where(column == source_company_id)
    ).scalars().all()
    for row in rows:
        setattr(row, company_field_name, target_company_id)
    return len(rows)


def _merge_company_source_priorities(
    db,
    *,
    org_id: uuid.UUID,
    source_company_id: uuid.UUID,
    target_company_id: uuid.UUID,
) -> tuple[int, int]:
    moved = 0
    merged = 0
    source_rows = db.execute(
        select(CompanySourcePriority).where(
            CompanySourcePriority.org_id == org_id,
            CompanySourcePriority.company_id == source_company_id,
        )
    ).scalars().all()
    for source_row in source_rows:
        existing = db.execute(
            select(CompanySourcePriority).where(
                CompanySourcePriority.org_id == org_id,
                CompanySourcePriority.company_id == target_company_id,
                CompanySourcePriority.source_key == source_row.source_key,
            )
        ).scalar_one_or_none()
        if existing is None:
            source_row.company_id = target_company_id
            moved += 1
            continue
        existing.priority_rank = min(int(existing.priority_rank), int(source_row.priority_rank))
        existing.is_active = bool(existing.is_active) or bool(source_row.is_active)
        db.delete(source_row)
        merged += 1
    return moved, merged


if __name__ == "__main__":
    raise SystemExit(main())
