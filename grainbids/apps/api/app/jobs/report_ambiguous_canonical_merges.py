from __future__ import annotations

import argparse
import json
import uuid
from collections import defaultdict

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import (
    canonical_key,
    canonical_location_name,
    canonical_source_name,
)


def _sorted_values(values: set[str]) -> list[str]:
    return sorted(values, key=lambda value: value.casefold())


def build_report(org_id: uuid.UUID) -> dict[str, object]:
    session = get_sessionmaker()()
    try:
        rows = session.execute(
            select(
                NormalizedPrice.location,
                NormalizedPrice.source_name,
            )
            .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
            .join(Source, Source.id == PriceSnapshot.source_id)
            .where(Source.org_id == org_id)
        ).all()

        location_groups: dict[str, set[str]] = defaultdict(set)
        company_groups: dict[str, set[str]] = defaultdict(set)

        for raw_location, raw_source_name in rows:
            location_text = (raw_location or "").strip()
            source_text = (raw_source_name or "").strip()

            canonical_location = canonical_location_name(location_text)
            location_key = canonical_key(canonical_location)
            if location_key and location_text and canonical_location:
                location_groups[location_key].add(location_text)

            canonical_company = canonical_source_name(source_text)
            company_key = canonical_key(canonical_company)
            if company_key and source_text and canonical_company:
                company_groups[company_key].add(source_text)

        location_candidates = []
        for key, variants in location_groups.items():
            if len(variants) <= 1:
                continue
            canonical = canonical_location_name(next(iter(variants)))
            location_candidates.append(
                {
                    "canonical_key": key,
                    "canonical_name": canonical,
                    "variant_count": len(variants),
                    "variants": _sorted_values(variants),
                }
            )

        company_candidates = []
        for key, variants in company_groups.items():
            if len(variants) <= 1:
                continue
            canonical = canonical_source_name(next(iter(variants)))
            company_candidates.append(
                {
                    "canonical_key": key,
                    "canonical_name": canonical,
                    "variant_count": len(variants),
                    "variants": _sorted_values(variants),
                }
            )

        location_candidates.sort(key=lambda row: (-int(row["variant_count"]), str(row["canonical_name"]).casefold()))
        company_candidates.sort(key=lambda row: (-int(row["variant_count"]), str(row["canonical_name"]).casefold()))

        return {
            "org_id": str(org_id),
            "location_merge_candidates": location_candidates,
            "company_merge_candidates": company_candidates,
            "location_candidate_count": len(location_candidates),
            "company_candidate_count": len(company_candidates),
        }
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Report potential canonical merge candidates.")
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument("--output", default="", help="Optional JSON output file path")
    args = parser.parse_args()

    org_id = uuid.UUID(args.org_id)
    report = build_report(org_id)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file_obj:
            json.dump(report, file_obj, indent=2)
        print(f"wrote_report={args.output}")
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
