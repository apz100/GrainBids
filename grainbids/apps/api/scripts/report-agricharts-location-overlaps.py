from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import uuid

import requests
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_key, canonical_location_name, canonical_source_name, source_scope


@dataclass(frozen=True)
class LocationSourceRow:
    location_name: str
    source_name: str


def _is_company_identity_source(source_name: str | None) -> bool:
    scope, label = source_scope(source_name)
    if scope != "company":
        return False
    key = canonical_key(label)
    if key is None:
        return False
    return key not in settings.canonical_aggregator_sources_set


def _normalized_location_key(location_name: str | None) -> str | None:
    normalized = canonical_location_name(location_name)
    return canonical_key(normalized)


def _load_location_source_rows(db, *, org_id: uuid.UUID) -> list[LocationSourceRow]:
    rows = db.execute(
        select(NormalizedPrice.location, Source.name)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(Source.org_id == org_id)
        .where(NormalizedPrice.location.is_not(None))
    ).all()
    output: list[LocationSourceRow] = []
    for location_name, source_name in rows:
        if not location_name or not source_name:
            continue
        output.append(
            LocationSourceRow(
                location_name=str(location_name),
                source_name=str(source_name),
            )
        )
    return output


def _load_agricharts_locations_from_url(url: str) -> list[str]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    html = response.text
    match = re.search(r'<select[^>]*id="locationFilter"[^>]*>(.*?)</select>', html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        raise ValueError("Could not find locationFilter select in Agricharts page")
    block = match.group(1)
    option_values = re.findall(r"<option[^>]*>(.*?)</option>", block, flags=re.IGNORECASE | re.DOTALL)
    output: list[str] = []
    seen: set[str] = set()
    for raw_value in option_values:
        cleaned = re.sub(r"<[^>]+>", "", raw_value)
        cleaned = (
            cleaned.replace("&nbsp;", " ")
            .replace("&#39;", "'")
            .replace("&amp;", "&")
            .strip()
        )
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned or cleaned.casefold() == "all locations":
            continue
        # Agricharts dropdown often appends commodity labels to town names.
        cleaned = re.sub(r"\s+(Corn|Soybeans?|Wheat|Barley|Oats)\b", "", cleaned, flags=re.IGNORECASE)
        normalized = canonical_location_name(cleaned) or cleaned
        key = canonical_key(normalized)
        if key is None or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    output.sort(key=lambda value: value.casefold())
    return output


def build_overlap_report(
    *,
    rows: list[LocationSourceRow],
    aggregator_source_name: str = "Agricharts",
    aggregator_locations_override: list[str] | None = None,
) -> dict[str, object]:
    aggregator_key = canonical_key(canonical_source_name(aggregator_source_name))
    if aggregator_key is None:
        raise ValueError(f"Invalid aggregator source name: {aggregator_source_name}")

    aggregator_locations: dict[str, str] = {}
    company_sources_by_location: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        source_display = canonical_source_name(row.source_name) or row.source_name
        source_key = canonical_key(source_display)
        if source_key is None:
            continue
        location_key = _normalized_location_key(row.location_name)
        if location_key is None:
            continue
        location_display = canonical_location_name(row.location_name) or row.location_name
        if source_key == aggregator_key:
            # Keep one stable display label per canonical location key.
            aggregator_locations.setdefault(location_key, location_display)
            continue
        if not _is_company_identity_source(source_display):
            continue
        company_sources_by_location[location_key].add(source_display)

    if aggregator_locations_override:
        for location_name in aggregator_locations_override:
            location_key = _normalized_location_key(location_name)
            if location_key is None:
                continue
            location_display = canonical_location_name(location_name) or location_name
            aggregator_locations.setdefault(location_key, location_display)

    overlaps: list[dict[str, object]] = []
    unmatched: list[str] = []
    overlap_counts_by_source: dict[str, int] = defaultdict(int)

    for location_key, display_name in sorted(aggregator_locations.items(), key=lambda item: item[1].casefold()):
        matching_sources = sorted(company_sources_by_location.get(location_key, set()))
        if not matching_sources:
            unmatched.append(display_name)
            continue
        for source_name in matching_sources:
            overlap_counts_by_source[source_name] += 1
        overlaps.append(
            {
                "location_name": display_name,
                "matching_company_sources": matching_sources,
                "matching_company_source_count": len(matching_sources),
            }
        )

    top_sources = sorted(
        [{"source_name": source_name, "overlap_location_count": count} for source_name, count in overlap_counts_by_source.items()],
        key=lambda row: (-int(row["overlap_location_count"]), str(row["source_name"]).casefold()),
    )

    return {
        "aggregator_source_name": canonical_source_name(aggregator_source_name) or aggregator_source_name,
        "aggregator_location_count": len(aggregator_locations),
        "overlap_location_count": len(overlaps),
        "unmatched_location_count": len(unmatched),
        "rows": overlaps,
        "unmatched_locations": unmatched,
        "top_company_sources_by_overlap": top_sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report Agricharts location overlaps against company sources using canonical location matching."
    )
    parser.add_argument("--org-id", required=True, help="Organization UUID")
    parser.add_argument("--aggregator-source-name", default="Agricharts", help="Aggregator source display name")
    parser.add_argument(
        "--agricharts-url",
        default="https://fmn1.agricharts.com/markets/cash.php",
        help="Agricharts URL to scrape full location dropdown from.",
    )
    parser.add_argument(
        "--use-url-locations",
        action="store_true",
        help="Use Agricharts location dropdown list from URL as the comparison baseline.",
    )
    parser.add_argument(
        "--show-unmatched",
        action="store_true",
        help="Include full unmatched location list in output.",
    )
    args = parser.parse_args()

    org_id = uuid.UUID(args.org_id)
    db = get_sessionmaker()()
    try:
        rows = _load_location_source_rows(db, org_id=org_id)
        location_override = _load_agricharts_locations_from_url(args.agricharts_url) if args.use_url_locations else None
        report = build_overlap_report(
            rows=rows,
            aggregator_source_name=args.aggregator_source_name,
            aggregator_locations_override=location_override,
        )
    finally:
        db.close()

    print(f"aggregator_source={report['aggregator_source_name']}")
    print(f"aggregator_location_count={report['aggregator_location_count']}")
    print(f"overlap_location_count={report['overlap_location_count']}")
    print(f"unmatched_location_count={report['unmatched_location_count']}")
    print("--- top_company_sources_by_overlap ---")
    for row in report["top_company_sources_by_overlap"]:
        print(f"{row['source_name']}\t{row['overlap_location_count']}")
    print("--- overlap_rows ---")
    for row in report["rows"]:
        joined = "; ".join(row["matching_company_sources"])
        print(f"{row['location_name']}\t{row['matching_company_source_count']}\t{joined}")
    if args.show_unmatched:
        print("--- unmatched_aggregator_locations ---")
        for location_name in report["unmatched_locations"]:
            print(location_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
