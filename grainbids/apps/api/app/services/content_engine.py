from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html import escape
import json
import math
import re
import statistics
from typing import Iterable, Mapping
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.routes.normalized_prices import _snapshot_freshness_filters
from app.core.config import settings
from app.models.content_draft import ContentDraft
from app.models.normalized_price import NormalizedPrice
from app.models.price_snapshot import PriceSnapshot
from app.models.source import Source


FACT_SCHEMA_VERSION = "1"
TEMPLATE_VERSION = "1"
ALLOWED_CADENCES = ("daily", "weekly")
ALLOWED_STATUSES = {"draft", "draft_needs_review", "blocked"}


@dataclass(frozen=True)
class RegionConfig:
    key: str
    display_name: str
    source_regions: tuple[str, ...]
    timezone_name: str
    currency: str
    commodities: tuple[str, ...]
    freshness_hours: int
    minimum_healthy_sources: int
    minimum_locations_per_commodity: int


REGIONS: dict[str, RegionConfig] = {
    "eastern_ontario": RegionConfig(
        key="eastern_ontario",
        display_name="Eastern Ontario",
        source_regions=("Eastern Ontario", "Ontario"),
        timezone_name="America/Toronto",
        currency="CAD",
        commodities=("Corn", "Soybeans", "Wheat"),
        freshness_hours=24,
        minimum_healthy_sources=2,
        minimum_locations_per_commodity=2,
    ),
}


@dataclass(frozen=True)
class ContentBundle:
    issue_key: str
    region_key: str
    region_name: str
    cadence: str
    status: str
    data_as_of: datetime | None
    generated_at: datetime
    input_fingerprint: str
    facts: dict[str, object]
    artifacts: dict[str, object]
    qa: dict[str, object]


@dataclass(frozen=True)
class DraftGeneration:
    draft: ContentDraft
    created: bool


def get_region_config(region: str) -> RegionConfig:
    key = _slug(region)
    if key in REGIONS:
        return REGIONS[key]
    for config in REGIONS.values():
        if region.strip().casefold() == config.display_name.casefold():
            return config
    raise ValueError(f"Unsupported content region '{region}'")


def list_region_keys() -> tuple[str, ...]:
    return tuple(sorted(REGIONS))


def load_content_rows(
    db: Session,
    *,
    org_id: uuid.UUID,
    region: RegionConfig,
) -> list[dict[str, object]]:
    query = (
        select(NormalizedPrice, PriceSnapshot, Source)
        .join(PriceSnapshot, PriceSnapshot.id == NormalizedPrice.snapshot_id)
        .join(Source, Source.id == PriceSnapshot.source_id)
        .where(
            Source.org_id == org_id,
            Source.is_active.is_(True),
            Source.collection_status.in_(("pilot", "active")),
            NormalizedPrice.is_canonical.is_(True),
            NormalizedPrice.commodity_name.in_(region.commodities),
            or_(
                Source.region.is_(None),
                Source.region == "",
                *(Source.region.ilike(f"%{value}%") for value in region.source_regions),
            ),
        )
    )
    for freshness_filter in _snapshot_freshness_filters(enforce_latest=True):
        query = query.where(freshness_filter)
    rows = db.execute(query).all()
    return [
        {
            "id": str(price.id),
            "snapshot_id": str(snapshot.id),
            "source_id": str(source.id),
            "source_name": source.name,
            "source_region": source.region,
            "source_active": source.is_active,
            "source_collection_status": source.collection_status,
            "source_confidence": _number(source.confidence_score),
            "currency": (source.currency_code or region.currency).upper(),
            "captured_at": snapshot.captured_at,
            "commodity": price.commodity_name,
            "location": price.location,
            "buyer_name": price.source_name or source.name,
            "delivery_label": price.delivery_label,
            "delivery_start": price.delivery_start,
            "delivery_end": price.delivery_end,
            "futures_month": price.futures_month,
            "futures_price": _number(price.futures_price),
            "basis": _basis_number(price.basis),
            "basis_change_strict": _basis_number(price.basis_change_strict),
            "cash_price_bu": _number(price.cash_price_bu),
            "cash_price_mt": _number(price.cash_price_mt),
            "is_canonical": price.is_canonical,
        }
        for price, snapshot, source in rows
    ]


def build_content_bundle(
    rows: Iterable[Mapping[str, object]],
    *,
    cadence: str,
    region: RegionConfig,
    generated_at: datetime | None = None,
) -> ContentBundle:
    cadence = cadence.strip().lower()
    if cadence not in ALLOWED_CADENCES:
        raise ValueError(f"cadence must be one of: {', '.join(ALLOWED_CADENCES)}")
    generated_at = _aware_datetime(generated_at or datetime.now(timezone.utc))
    input_rows = [_canonical_input_row(row, region=region) for row in rows]
    input_rows.sort(key=lambda row: str(row["id"]))
    fingerprint = _fingerprint(input_rows, cadence=cadence, region=region)
    issue_key = _issue_key(cadence=cadence, region=region, generated_at=generated_at)

    warnings: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    fresh_rows: list[dict[str, object]] = []
    for row in input_rows:
        reason = _exclusion_reason(row, region=region, generated_at=generated_at)
        if reason:
            excluded.append({"row_id": row["id"], "reason": reason})
        else:
            fresh_rows.append(row)

    excluded_counts = _count_reasons(excluded)
    if excluded_counts:
        warnings.append({"code": "rows_excluded", "counts": excluded_counts})

    source_ids = sorted({str(row["source_id"]) for row in fresh_rows})
    location_names = sorted({str(row["location"]) for row in fresh_rows})
    data_as_of = max((_as_datetime(row["captured_at"]) for row in fresh_rows), default=None)
    if not fresh_rows:
        failures.append({"code": "no_fresh_canonical_rows"})
    if len(source_ids) < region.minimum_healthy_sources:
        failures.append(
            {
                "code": "minimum_source_coverage",
                "actual": len(source_ids),
                "required": region.minimum_healthy_sources,
            }
        )

    facts: list[dict[str, object]] = []
    if fresh_rows:
        facts.append(_coverage_fact(fresh_rows, region=region, data_as_of=data_as_of))

    comparable_rows: list[dict[str, object]] = []
    commodities = sorted({str(row["commodity"]) for row in fresh_rows})
    for commodity in commodities:
        commodity_rows = [row for row in fresh_rows if row["commodity"] == commodity]
        commodity_locations = {str(row["location"]) for row in commodity_rows}
        if len(commodity_locations) < region.minimum_locations_per_commodity:
            warnings.append(
                {
                    "code": "minimum_location_coverage",
                    "commodity": commodity,
                    "actual": len(commodity_locations),
                    "required": region.minimum_locations_per_commodity,
                }
            )
            continue
        comparable_rows.extend(commodity_rows)

    facts.extend(_cash_summary_facts(comparable_rows, region=region))
    facts.extend(_strict_basis_change_facts(comparable_rows, region=region))
    if fresh_rows and len(facts) <= 1:
        failures.append({"code": "no_publishable_market_facts"})

    status = "blocked" if failures else "draft_needs_review" if warnings else "draft"
    facts.sort(key=lambda fact: str(fact["fact_id"]))
    fact_pack = {
        "schema_version": FACT_SCHEMA_VERSION,
        "issue_key": issue_key,
        "region_key": region.key,
        "region_name": region.display_name,
        "content_cadence": cadence,
        "generated_at": generated_at.isoformat(),
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "currency": region.currency,
        "coverage": {
            "healthy_sources": len(source_ids),
            "locations": len(location_names),
            "commodities": commodities,
        },
        "facts": facts,
        "warnings": warnings,
        "input_fingerprint": fingerprint,
    }
    qa = {
        "status": "failed" if failures else "warning" if warnings else "passed",
        "checks": [
            {
                "name": "freshness",
                "status": "pass" if fresh_rows else "fail",
                "freshness_hours": region.freshness_hours,
            },
            {
                "name": "source_coverage",
                "status": "pass" if len(source_ids) >= region.minimum_healthy_sources else "fail",
                "actual": len(source_ids),
                "required": region.minimum_healthy_sources,
            },
            {"name": "comparability", "status": "pass" if len(facts) > 1 else "fail"},
            {"name": "currency_and_units", "status": "pass" if not excluded_counts.get("currency_mismatch") else "warn"},
            {"name": "fact_lineage", "status": "pass" if all(fact.get("source_row_ids") for fact in facts) else "fail"},
        ],
        "warnings": warnings,
        "failures": failures,
        "excluded_rows": excluded,
    }
    artifacts = _render_artifacts(
        fact_pack,
        status=status,
        cadence=cadence,
        region=region,
        generated_at=generated_at,
    )
    _validate_artifact_lineage(fact_pack, artifacts)
    if status not in ALLOWED_STATUSES:
        raise AssertionError(f"Unsupported persisted content status: {status}")
    return ContentBundle(
        issue_key=issue_key,
        region_key=region.key,
        region_name=region.display_name,
        cadence=cadence,
        status=status,
        data_as_of=data_as_of,
        generated_at=generated_at,
        input_fingerprint=fingerprint,
        facts=fact_pack,
        artifacts=artifacts,
        qa=qa,
    )


def generate_content_draft(
    db: Session,
    *,
    org_id: uuid.UUID,
    cadence: str,
    region_key: str = "eastern_ontario",
    generated_at: datetime | None = None,
    rows: Iterable[Mapping[str, object]] | None = None,
) -> DraftGeneration:
    region = get_region_config(region_key)
    input_rows = list(rows) if rows is not None else load_content_rows(db, org_id=org_id, region=region)
    bundle = build_content_bundle(input_rows, cadence=cadence, region=region, generated_at=generated_at)
    existing = db.execute(
        select(ContentDraft).where(
            ContentDraft.org_id == org_id,
            ContentDraft.issue_key == bundle.issue_key,
            ContentDraft.input_fingerprint == bundle.input_fingerprint,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return DraftGeneration(draft=existing, created=False)

    draft = ContentDraft(
        org_id=org_id,
        issue_key=bundle.issue_key,
        region_key=bundle.region_key,
        region_name=bundle.region_name,
        cadence=bundle.cadence,
        status=bundle.status,
        data_as_of=bundle.data_as_of,
        generated_at=bundle.generated_at,
        input_fingerprint=bundle.input_fingerprint,
        fact_schema_version=FACT_SCHEMA_VERSION,
        template_version=TEMPLATE_VERSION,
        facts_json=bundle.facts,
        artifacts_json=bundle.artifacts,
        qa_json=bundle.qa,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return DraftGeneration(draft=draft, created=True)


def _canonical_input_row(row: Mapping[str, object], *, region: RegionConfig) -> dict[str, object]:
    captured_at = _as_datetime(row.get("captured_at"))
    return {
        "id": str(row.get("id") or ""),
        "snapshot_id": str(row.get("snapshot_id") or ""),
        "source_id": str(row.get("source_id") or row.get("source_name") or ""),
        "source_name": str(row.get("source_name") or "").strip(),
        "source_active": row.get("source_active", True),
        "source_collection_status": str(row.get("source_collection_status") or "active").strip().lower(),
        "currency": str(row.get("currency") or region.currency).strip().upper(),
        "captured_at": captured_at.isoformat() if captured_at else None,
        "commodity": str(row.get("commodity") or row.get("commodity_name") or "").strip(),
        "location": str(row.get("location") or "").strip(),
        "buyer_name": str(row.get("buyer_name") or row.get("company_name") or row.get("source_name") or "").strip(),
        "delivery_label": _clean(row.get("delivery_label")),
        "delivery_start": _clean(row.get("delivery_start")),
        "delivery_end": _clean(row.get("delivery_end")),
        "futures_month": _clean(row.get("futures_month")),
        "basis": _basis_number(row.get("basis")),
        "basis_change_strict": _basis_number(row.get("basis_change_strict")),
        "strict_prior_row_id": _clean(row.get("strict_prior_row_id")),
        "strict_prior_delivery_label": _clean(row.get("strict_prior_delivery_label")),
        "strict_prior_delivery_start": _clean(row.get("strict_prior_delivery_start")),
        "strict_prior_delivery_end": _clean(row.get("strict_prior_delivery_end")),
        "strict_prior_futures_month": _clean(row.get("strict_prior_futures_month")),
        "cash_price_bu": _number(row.get("cash_price_bu")),
        "cash_price_mt": _number(row.get("cash_price_mt")),
        "is_canonical": row.get("is_canonical", True),
    }


def _exclusion_reason(row: Mapping[str, object], *, region: RegionConfig, generated_at: datetime) -> str | None:
    if not row.get("id") or not row.get("source_id"):
        return "missing_lineage"
    if row.get("is_canonical") is False:
        return "non_canonical"
    if row.get("source_active") is False:
        return "inactive_source"
    if row.get("source_collection_status") not in {"pilot", "active"}:
        return "ineligible_source_status"
    if row.get("currency") != region.currency:
        return "currency_mismatch"
    captured_at = _as_datetime(row.get("captured_at"))
    if captured_at is None:
        return "missing_capture_time"
    age_hours = (generated_at - captured_at).total_seconds() / 3600
    if age_hours > region.freshness_hours:
        return "stale"
    if not row.get("commodity") or not row.get("location"):
        return "missing_market_identity"
    if _number(row.get("cash_price_bu")) is None and _number(row.get("cash_price_mt")) is None:
        return "missing_cash_price"
    return None


def _coverage_fact(
    rows: list[dict[str, object]],
    *,
    region: RegionConfig,
    data_as_of: datetime | None,
) -> dict[str, object]:
    sources = {str(row["source_id"]) for row in rows}
    locations = {str(row["location"]) for row in rows}
    row_ids = sorted({str(row["id"]) for row in rows})
    return {
        "fact_id": "coverage:regional",
        "fact_type": "coverage",
        "healthy_sources": len(sources),
        "locations": len(locations),
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "currency": region.currency,
        "source_row_ids": row_ids,
        "claim_text": f"Coverage includes {len(sources)} sources and {len(locations)} locations.",
    }


def _cash_summary_facts(rows: list[dict[str, object]], *, region: RegionConfig) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[tuple[dict[str, object], float]]] = {}
    for row in rows:
        delivery_key = _delivery_bucket(row)
        if delivery_key is None:
            continue
        for field, unit_suffix in (("cash_price_bu", "bu"), ("cash_price_mt", "MT")):
            value = _number(row.get(field))
            if value is None:
                continue
            unit = f"{region.currency}/{unit_suffix}"
            grouped.setdefault((str(row["commodity"]), delivery_key, unit), []).append((row, value))

    facts: list[dict[str, object]] = []
    for (commodity, delivery_key, unit), observations in sorted(grouped.items()):
        observations.sort(key=lambda item: (item[1], str(item[0]["id"])))
        low_row, low = observations[0]
        high_row, high = observations[-1]
        values = [value for _row, value in observations]
        fact_id = f"cash:{_slug(commodity)}:{_short_hash(delivery_key)}:{unit.split('/')[-1].lower()}"
        delivery_label = str(high_row.get("delivery_label") or delivery_key)
        decimals = 2
        claim = (
            f"{commodity} — {delivery_label}: listed range {low:.{decimals}f} to {high:.{decimals}f} "
            f"{unit} across {len(values)} posted bids; highest listed at {high_row['location']}, before freight."
        )
        facts.append(
            {
                "fact_id": fact_id,
                "fact_type": "posted_bid_summary",
                "commodity": commodity,
                "delivery_bucket": delivery_key,
                "delivery_label": delivery_label,
                "futures_month": high_row.get("futures_month"),
                "low": low,
                "high": high,
                "median": statistics.median(values),
                "count": len(values),
                "highest_location": high_row["location"],
                "highest_buyer": high_row["buyer_name"],
                "currency": region.currency,
                "unit": unit,
                "freight_included": False,
                "source_row_ids": sorted({str(row["id"]) for row, _value in observations}),
                "claim_text": claim,
            }
        )
    return facts


def _strict_basis_change_facts(rows: list[dict[str, object]], *, region: RegionConfig) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for row in rows:
        change = _number(row.get("basis_change_strict"))
        delivery_key = _delivery_bucket(row)
        futures_month = _clean(row.get("futures_month"))
        if change is None or delivery_key is None or futures_month is None or not _strict_metadata_matches(row):
            continue
        comparison_key = "|".join(
            [str(row["commodity"]), str(row["location"]), delivery_key, futures_month, region.currency, "bu"]
        )
        fact_id = f"basis-change:{_short_hash(comparison_key)}"
        delivery_label = str(row.get("delivery_label") or delivery_key)
        claim = (
            f"{row['buyer_name']} — {row['location']} {row['commodity']} {delivery_label} basis changed "
            f"{change:+.2f} {region.currency}/bu versus the previous exact {futures_month} futures comparison."
        )
        facts.append(
            {
                "fact_id": fact_id,
                "fact_type": "strict_basis_change",
                "commodity": row["commodity"],
                "location": row["location"],
                "buyer_name": row["buyer_name"],
                "delivery_bucket": delivery_key,
                "delivery_label": delivery_label,
                "futures_month": futures_month,
                "value": change,
                "currency": region.currency,
                "unit": f"{region.currency}/bu",
                "comparison_key": comparison_key,
                "formula": "stored basis_change_strict; canonical exact-match policy",
                "source_row_ids": sorted(
                    {str(row["id"]), *([str(row["strict_prior_row_id"])] if row.get("strict_prior_row_id") else [])}
                ),
                "claim_text": claim,
            }
        )
    return facts


def _render_artifacts(
    fact_pack: Mapping[str, object],
    *,
    status: str,
    cadence: str,
    region: RegionConfig,
    generated_at: datetime,
) -> dict[str, object]:
    facts = list(fact_pack["facts"])
    market_facts = [fact for fact in facts if fact["fact_type"] == "posted_bid_summary"]
    change_facts = [fact for fact in facts if fact["fact_type"] == "strict_basis_change"]
    coverage_fact = next((fact for fact in facts if fact["fact_type"] == "coverage"), None)
    local = generated_at.astimezone(ZoneInfo(region.timezone_name))
    cadence_label = "daily snapshot" if cadence == "daily" else "weekly market report"
    subject = f"GrainBids {region.display_name} {cadence_label} — {local:%B} {local.day}, {local:%Y}"
    claims: list[dict[str, str]] = []
    lines = [subject, ""]
    if status == "blocked":
        lines.append("Draft blocked by data-quality checks. Review the attached QA report before using this content.")
    else:
        if coverage_fact:
            coverage_text = str(coverage_fact["claim_text"])
            lines.extend([coverage_text, ""])
            claims.append({"fact_id": str(coverage_fact["fact_id"]), "text": coverage_text})
        lines.append("POSTED BIDS")
        for fact in market_facts:
            text = str(fact["claim_text"])
            lines.append(text)
            claims.append({"fact_id": str(fact["fact_id"]), "text": text})
        lines.extend(["", "STRICT CHANGES"])
        if change_facts:
            for fact in change_facts:
                text = str(fact["claim_text"])
                lines.append(text)
                claims.append({"fact_id": str(fact["fact_id"]), "text": text})
        else:
            lines.append("No comparable strict basis changes met the publication rules.")
        lines.extend(
            [
                "",
                "Posted-bid snapshot only. Freight is not included. Verify grade, delivery window, futures contract, currency, and current buyer terms.",
                f"View current bids: {settings.market_report_public_url.rstrip('/')}",
            ]
        )
    text = "\n".join(lines)
    email = {
        "publication_status": status,
        "subject": subject,
        "text": text,
        "html": "<!doctype html><html><body>" + "".join(f"<p>{escape(line)}</p>" for line in lines) + "</body></html>",
        "claims": claims,
    }

    social: list[dict[str, object]] = []
    if status != "blocked":
        for index, fact in enumerate(market_facts[:2], start=1):
            social_text = str(fact["claim_text"]) + " Posted bids; freight not included."
            social.append(
                {
                    "variant": f"snapshot-{index}",
                    "publication_status": status,
                    "text": social_text,
                    "claims": [{"fact_id": fact["fact_id"], "text": str(fact["claim_text"])}],
                }
            )
        if coverage_fact:
            coverage_text = str(coverage_fact["claim_text"])
            social.append(
                {
                    "variant": "coverage",
                    "publication_status": status,
                    "text": coverage_text + f" View current bids: {settings.market_report_public_url.rstrip('/')}",
                    "claims": [{"fact_id": coverage_fact["fact_id"], "text": coverage_text}],
                }
            )

    site_tables = [
        {
            "fact_id": fact["fact_id"],
            "commodity": fact["commodity"],
            "delivery": fact["delivery_label"],
            "low": fact["low"],
            "high": fact["high"],
            "count": fact["count"],
            "currency": fact["currency"],
            "unit": fact["unit"],
        }
        for fact in market_facts
    ]
    site = {
        "publication_status": status,
        "title": subject,
        "slug": f"{region.key}-{cadence}-{local:%Y-%m-%d}",
        "region": region.display_name,
        "local_date": local.date().isoformat(),
        "data_as_of": fact_pack.get("data_as_of"),
        "summary": "Deterministic posted-bid snapshot; freight is not included.",
        "tables": site_tables,
        "methodology": "Only comparable delivery, currency and unit buckets are summarized.",
        "canonical_url": settings.market_report_public_url.rstrip("/"),
        "claims": [
            {"fact_id": fact["fact_id"], "text": str(fact["claim_text"])} for fact in market_facts
        ],
    }
    return {"email": email, "social": social, "site": site}


def _validate_artifact_lineage(fact_pack: Mapping[str, object], artifacts: Mapping[str, object]) -> None:
    fact_ids = {str(fact["fact_id"]) for fact in fact_pack["facts"]}
    claims: list[Mapping[str, object]] = list(artifacts["email"]["claims"])
    claims.extend(artifacts["site"]["claims"])
    for variant in artifacts["social"]:
        claims.extend(variant["claims"])
    for claim in claims:
        if str(claim.get("fact_id")) not in fact_ids:
            raise ValueError(f"Rendered claim lacks valid fact lineage: {claim!r}")


def _delivery_bucket(row: Mapping[str, object]) -> str | None:
    start = _clean(row.get("delivery_start"))
    end = _clean(row.get("delivery_end"))
    if start or end:
        return f"{start or '?'}:{end or '?'}"
    label = _clean(row.get("delivery_label"))
    if label and label.casefold() not in {"n/a", "na", "unknown", "-"}:
        return re.sub(r"\s+", " ", label.casefold())
    return None


def _strict_metadata_matches(row: Mapping[str, object]) -> bool:
    prior_values = (
        row.get("strict_prior_delivery_label"),
        row.get("strict_prior_delivery_start"),
        row.get("strict_prior_delivery_end"),
        row.get("strict_prior_futures_month"),
    )
    if not any(prior_values):
        # `basis_change_strict` is produced by the canonical exact-match policy.
        return True
    prior_row = {
        "delivery_label": row.get("strict_prior_delivery_label"),
        "delivery_start": row.get("strict_prior_delivery_start"),
        "delivery_end": row.get("strict_prior_delivery_end"),
    }
    return (
        _delivery_bucket(row) == _delivery_bucket(prior_row)
        and _clean(row.get("futures_month")) == _clean(row.get("strict_prior_futures_month"))
    )


def _issue_key(*, cadence: str, region: RegionConfig, generated_at: datetime) -> str:
    local = generated_at.astimezone(ZoneInfo(region.timezone_name))
    if cadence == "daily":
        suffix = local.date().isoformat()
    else:
        iso_year, iso_week, _ = local.isocalendar()
        suffix = f"{iso_year}-W{iso_week:02d}"
    return f"{region.key}:{cadence}:{suffix}"


def _fingerprint(rows: list[dict[str, object]], *, cadence: str, region: RegionConfig) -> str:
    payload = {
        "fact_schema_version": FACT_SCHEMA_VERSION,
        "template_version": TEMPLATE_VERSION,
        "region": region.key,
        "cadence": cadence,
        "rows": rows,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _count_reasons(excluded: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in excluded:
        reason = str(item["reason"])
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _basis_number(value: object) -> float | None:
    number = _number(value)
    if number is not None and abs(number) >= 10:
        return number / 100
    return number


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_datetime(value)
    if isinstance(value, str) and value:
        try:
            return _aware_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _short_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]
