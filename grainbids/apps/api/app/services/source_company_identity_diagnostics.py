from __future__ import annotations

from collections import defaultdict
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.location import Location
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source
from app.services.market_canonicalization import canonical_source_name
from app.services.upload_csv import _source_creates_company_identity


def list_ambiguous_location_company_candidates(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    limit: int = 25,
) -> dict[str, object]:
    trusted_company_name_by_id, trusted_company_ids = _trusted_companies(db, org_id=org_id)
    if not trusted_company_ids:
        return {"rows": [], "total_count": 0}

    query = (
        select(NormalizedPrice.location_id, NormalizedPrice.company_id, NormalizedPrice.source_name)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(
            Source.org_id == org_id,
            NormalizedPrice.location_id.is_not(None),
            NormalizedPrice.company_id.is_not(None),
            NormalizedPrice.company_id.in_(trusted_company_ids),
        )
    )
    if source_id is not None:
        query = query.where(Source.id == source_id)

    candidate_rows = db.execute(query).all()
    by_location: dict[uuid.UUID, dict[str, object]] = {}

    for location_id, company_id, source_name in candidate_rows:
        if location_id is None or company_id is None:
            continue
        if not _source_creates_company_identity(source_name):
            continue
        entry = by_location.get(location_id)
        if entry is None:
            entry = {
                "company_counts": defaultdict(int),
                "source_counts": defaultdict(int),
            }
            by_location[location_id] = entry
        entry["company_counts"][company_id] += 1
        source_label = canonical_source_name(source_name) or (source_name or "").strip() or "Unknown"
        entry["source_counts"][source_label] += 1

    if not by_location:
        return {"rows": [], "total_count": 0}

    location_rows = (
        db.execute(
            select(Location).where(
                Location.org_id == org_id,
                Location.id.in_(set(by_location.keys())),
            )
        )
        .scalars()
        .all()
    )

    for location in location_rows:
        entry = by_location.get(location.id)
        if entry is None:
            continue
        current_company_id = location.company_id if location.company_id in trusted_company_ids else None
        entry["location"] = location
        entry["current_company_id"] = current_company_id
        if current_company_id is not None and current_company_id not in entry["company_counts"]:
            entry["company_counts"][current_company_id] = 0

    rows = _build_ambiguous_location_rows(
        by_location=by_location,
        trusted_company_name_by_id=trusted_company_name_by_id,
    )
    return {"rows": rows[:limit], "total_count": len(rows)}


def _build_ambiguous_location_rows(
    *,
    by_location: dict[uuid.UUID, dict[str, object]],
    trusted_company_name_by_id: dict[uuid.UUID, str],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for location_id, payload in by_location.items():
        location = payload.get("location")
        if not isinstance(location, Location):
            continue
        company_counts = payload.get("company_counts")
        source_counts = payload.get("source_counts")
        if not isinstance(company_counts, dict):
            continue
        if len(company_counts) < 2:
            continue

        total_rows = sum(int(count) for count in company_counts.values())
        candidate_companies = [
            {
                "company_id": str(company_id),
                "company_name": trusted_company_name_by_id.get(company_id, "Unknown"),
                "row_count": int(count),
            }
            for company_id, count in company_counts.items()
        ]
        candidate_companies.sort(key=lambda row: (-int(row["row_count"]), str(row["company_name"]).casefold()))

        top_sources: list[dict[str, object]] = []
        if isinstance(source_counts, dict):
            top_sources = [
                {"source_name": source_name, "row_count": int(count)}
                for source_name, count in source_counts.items()
            ]
            top_sources.sort(key=lambda row: (-int(row["row_count"]), str(row["source_name"]).casefold()))
            top_sources = top_sources[:5]

        current_company_id = payload.get("current_company_id")
        current_company_name = None
        if isinstance(current_company_id, uuid.UUID):
            current_company_name = trusted_company_name_by_id.get(current_company_id)

        output.append(
            {
                "location_id": str(location_id),
                "location_name": location.name,
                "location_region": location.region,
                "candidate_company_count": len(candidate_companies),
                "candidate_row_count": int(total_rows),
                "current_company_id": str(current_company_id) if isinstance(current_company_id, uuid.UUID) else None,
                "current_company_name": current_company_name,
                "candidate_companies": candidate_companies,
                "top_sources": top_sources,
            }
        )

    output.sort(
        key=lambda row: (
            -int(row["candidate_company_count"]),
            -int(row["candidate_row_count"]),
            str(row["location_name"]).casefold(),
        )
    )
    return output


def _trusted_companies(
    db: Session,
    *,
    org_id: uuid.UUID,
) -> tuple[dict[uuid.UUID, str], set[uuid.UUID]]:
    rows = db.execute(select(Company.id, Company.name).where(Company.org_id == org_id)).all()
    trusted_company_name_by_id: dict[uuid.UUID, str] = {}
    trusted_company_ids: set[uuid.UUID] = set()
    for company_id, company_name in rows:
        if company_id is None or not company_name:
            continue
        if not _source_creates_company_identity(company_name):
            continue
        trusted_company_name_by_id[company_id] = company_name
        trusted_company_ids.add(company_id)
    return trusted_company_name_by_id, trusted_company_ids
