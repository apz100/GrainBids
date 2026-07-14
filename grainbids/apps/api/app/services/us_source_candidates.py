from __future__ import annotations

from dataclasses import dataclass
import tomllib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source import Source
from app.platform.market_data.service import get_sources_path
from app.services.source_registry import get_adapter


SUPPORTED_US_SOURCE_TYPES = {
    "agricharts": "us_agricharts",
    "dtn": "us_dtn",
}


@dataclass(frozen=True)
class USSourceCandidate:
    name: str
    url: str
    adapter_key: str


def load_us_source_candidates() -> list[USSourceCandidate]:
    config_path = get_sources_path() / "us_elevators_urls.toml"
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)

    candidates: list[USSourceCandidate] = []
    seen_urls: set[str] = set()
    seen_names: set[str] = set()
    for row in config.get("us", {}).get("elevators", []):
        source_type = str(row.get("type", "")).strip().lower()
        adapter_key = SUPPORTED_US_SOURCE_TYPES.get(source_type)
        name = str(row.get("name", "")).strip()
        url = str(row.get("url", "")).strip()
        name_key = name.casefold()
        if (
            not row.get("enabled")
            or adapter_key is None
            or not name
            or not url
            or url in seen_urls
            or name_key in seen_names
        ):
            continue
        get_adapter(adapter_key)
        seen_urls.add(url)
        seen_names.add(name_key)
        candidates.append(USSourceCandidate(name=name, url=url, adapter_key=adapter_key))
    return candidates


def seed_us_source_candidates(db: Session, *, org_id: uuid.UUID) -> dict[str, int]:
    existing_sources = db.execute(select(Source).where(Source.org_id == org_id)).scalars().all()
    existing_urls = {source.url.strip() for source in existing_sources if source.url and source.url.strip()}
    existing_names = {source.name.strip().casefold() for source in existing_sources if source.name.strip()}
    created = 0
    skipped = 0
    for candidate in load_us_source_candidates():
        name_key = candidate.name.casefold()
        if candidate.url in existing_urls or name_key in existing_names:
            skipped += 1
            continue
        adapter = get_adapter(candidate.adapter_key)
        db.add(
            Source(
                org_id=org_id,
                name=candidate.name,
                adapter_key=candidate.adapter_key,
                source_type="automated",
                url=candidate.url,
                region="United States",
                country_code="US",
                currency_code="USD",
                collection_status="candidate",
                polling_interval_minutes=adapter.default_poll_minutes,
                timeout_seconds=adapter.default_timeout_seconds,
                max_retries=2,
                is_active=False,
            )
        )
        existing_urls.add(candidate.url)
        existing_names.add(name_key)
        created += 1
    if created:
        db.commit()
    return {"created": created, "skipped": skipped}
