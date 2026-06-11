from __future__ import annotations

import argparse
import csv
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report active Agricharts locations without company mappings, sorted by row frequency."
    )
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument(
        "--output-csv",
        default="",
        help="Optional output CSV path. If omitted, prints rows to stdout.",
    )
    parser.add_argument("--limit", type=int, default=500, help="Maximum rows to return")
    parser.add_argument(
        "--location-kind",
        default="elevator",
        choices=["elevator", "benchmark", "all"],
        help="Filter output to one label class. Default is elevator for mapping queue usage.",
    )
    args = parser.parse_args()

    org_id = uuid.UUID(args.org_id)
    db = get_sessionmaker()()
    try:
        latest = _latest_agricharts_snapshot_time(db, org_id=org_id)
        if latest is None:
            raise SystemExit("No Agricharts snapshot found for this org.")
        rows = _active_unmapped_rows(
            db,
            org_id=org_id,
            captured_at=latest,
            limit=max(1, int(args.limit)),
            location_kind=args.location_kind,
        )
    finally:
        db.close()

    if args.output_csv:
        output_path = Path(args.output_csv).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["location", "row_count", "location_kind", "latest_captured_at"],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print(f"output={output_path}")
    else:
        for row in rows:
            print(
                "{location}\trows={row_count}\tkind={location_kind}\tcaptured_at={latest_captured_at}".format(
                    **row
                )
            )
    print(f"count={len(rows)}")
    return 0


def _latest_agricharts_snapshot_time(db, *, org_id: uuid.UUID):
    return db.execute(
        select(func.max(PriceSnapshot.captured_at))
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id)
        .where(func.lower(func.trim(Source.name)) == "agricharts")
    ).scalar_one_or_none()


def _active_unmapped_rows(
    db,
    *,
    org_id: uuid.UUID,
    captured_at,
    limit: int,
    location_kind: str,
) -> list[dict[str, object]]:
    active_rows = db.execute(
        select(NormalizedPrice.location, func.count(NormalizedPrice.id))
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id)
        .where(func.lower(func.trim(Source.name)) == "agricharts")
        .where(PriceSnapshot.captured_at == captured_at)
        .group_by(NormalizedPrice.location)
    ).all()

    mapped_rows = db.execute(
        select(LocationCompanyMapping.raw_location_name, LocationCompanyMapping.source_url)
        .where(LocationCompanyMapping.org_id == org_id)
    ).all()
    mapped_keys = set()
    for raw_location_name, source_url in mapped_rows:
        if source_url and "fmn1.agricharts.com/markets/cash.php" in source_url.casefold():
            key = canonical_key(canonical_location_name(raw_location_name))
            if key:
                mapped_keys.add(key)

    result: list[dict[str, object]] = []
    for location_name, row_count in active_rows:
        normalized = canonical_location_name(location_name)
        if normalized is None:
            continue
        kind = location_label_kind(normalized)
        if location_kind != "all" and kind != location_kind:
            continue
        key = canonical_key(normalized)
        if key is None or key in mapped_keys:
            continue
        result.append(
            {
                "location": normalized,
                "row_count": int(row_count or 0),
                "location_kind": kind,
                "latest_captured_at": captured_at.isoformat() if captured_at else None,
            }
        )

    result.sort(key=lambda row: (-int(row["row_count"]), str(row["location"]).casefold()))
    return result[:limit]


if __name__ == "__main__":
    raise SystemExit(main())
