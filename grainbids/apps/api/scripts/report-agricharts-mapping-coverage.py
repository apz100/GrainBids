from __future__ import annotations

import argparse
from pathlib import Path
import sys
import uuid

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import get_sessionmaker
from app.models.location_company_mapping import LocationCompanyMapping
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_key, canonical_location_name, location_label_kind


AGRICHARTS_MARKER = "fmn1.agricharts.com/markets/cash.php"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report active Agricharts location mapping coverage and cap progress."
    )
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument("--target", type=int, default=65, help="Active mapped elevator target for cap checkpoint.")
    args = parser.parse_args()

    org_id = uuid.UUID(args.org_id)
    target = max(1, int(args.target))

    db = get_sessionmaker()()
    try:
        latest = _latest_agricharts_snapshot_time(db, org_id=org_id)
        if latest is None:
            raise SystemExit("No Agricharts snapshot found for this org.")

        active_locations = _active_agricharts_location_names(db, org_id=org_id, captured_at=latest)
        active_elevators = {name for name in active_locations if location_label_kind(name) == "elevator"}

        mapped_locations = _mapped_agricharts_location_names(db, org_id=org_id)
        mapped_active = active_locations.intersection(mapped_locations)
        mapped_active_elevators = active_elevators.intersection(mapped_locations)

        total_active = len(active_locations)
        total_active_elevators = len(active_elevators)
        mapped_count = len(mapped_active)
        mapped_elevator_count = len(mapped_active_elevators)
        unmapped_count = total_active - mapped_count
        unmapped_elevator_count = total_active_elevators - mapped_elevator_count

        print(f"latest_captured_at={latest.isoformat()}")
        print(f"active_locations_total={total_active}")
        print(f"active_elevator_locations_total={total_active_elevators}")
        print(f"active_mapped_locations={mapped_count}")
        print(f"active_mapped_elevator_locations={mapped_elevator_count}")
        print(f"active_unmapped_locations={unmapped_count}")
        print(f"active_unmapped_elevator_locations={unmapped_elevator_count}")
        print(f"target_active_mapped_elevators={target}")
        print(f"target_reached={'yes' if mapped_elevator_count >= target else 'no'}")
        return 0
    finally:
        db.close()


def _latest_agricharts_snapshot_time(db, *, org_id: uuid.UUID):
    return db.execute(
        select(func.max(PriceSnapshot.captured_at))
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id)
        .where(func.lower(func.trim(Source.name)) == "agricharts")
    ).scalar_one_or_none()


def _active_agricharts_location_names(db, *, org_id: uuid.UUID, captured_at) -> set[str]:
    rows = db.execute(
        select(NormalizedPrice.location)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id)
        .where(func.lower(func.trim(Source.name)) == "agricharts")
        .where(PriceSnapshot.captured_at == captured_at)
    ).all()
    names: set[str] = set()
    for (location_name,) in rows:
        normalized = canonical_location_name(location_name)
        key = canonical_key(normalized)
        if normalized and key:
            names.add(normalized)
    return names


def _mapped_agricharts_location_names(db, *, org_id: uuid.UUID) -> set[str]:
    rows = db.execute(
        select(LocationCompanyMapping.raw_location_name, LocationCompanyMapping.source_url)
        .where(LocationCompanyMapping.org_id == org_id)
    ).all()
    names: set[str] = set()
    for raw_location_name, source_url in rows:
        if not source_url or AGRICHARTS_MARKER not in source_url.casefold():
            continue
        normalized = canonical_location_name(raw_location_name)
        key = canonical_key(normalized)
        if normalized and key:
            names.add(normalized)
    return names


if __name__ == "__main__":
    raise SystemExit(main())
