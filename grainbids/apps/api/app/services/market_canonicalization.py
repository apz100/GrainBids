from __future__ import annotations

import re


NULL_LIKE = {"nan", "none", "null", "na", "n/a", "-"}
REGION_SOURCE_LABELS = {
    "eastern ontario cash bids": "Eastern Ontario",
    "eastern ontario daily file": "Eastern Ontario",
    "ontario cash bids": "Ontario",
    "ontario daily file": "Ontario",
}
LOCATION_CANONICAL_OVERRIDES = {
    # Known deterministic typo/variant cleanups
    "starffordville": "Straffordville",
    "staffordville": "Straffordville",
    # Source-emitted variants that should map to one market location label
    "toledo": "Toledo Elevator",
    "toledo corn": "Toledo Elevator",
    "toledo soybeans": "Toledo Elevator",
}


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value).strip())
    if not cleaned:
        return None
    if cleaned.casefold() in NULL_LIKE:
        return None
    return cleaned


def canonical_key(value: str | None) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    return normalized.casefold()


def canonical_source_name(source_name: str | None) -> str | None:
    normalized = normalize_text(source_name)
    if normalized is None:
        return None
    aliases = {
        "glg": "GLG",
        "g.l.g.": "GLG",
        "agricharts": "Agricharts",
        "andersons": "Andersons",
        "the andersons": "Andersons",
        "hensall": "Hensall",
        "snobelen": "Snobelen",
        "wanstead": "Wanstead",
        "eastern ontario cash bids": "Eastern Ontario Cash Bids",
        "eastern ontario daily file": "Eastern Ontario Daily File",
        "ontario cash bids": "Ontario Cash Bids",
        "ontario daily file": "Ontario Daily File",
    }
    return aliases.get(normalized.casefold(), normalized)


def canonical_commodity_name(commodity_name: str | None) -> str | None:
    normalized = normalize_text(commodity_name)
    if normalized is None:
        return None
    aliases = {
        "corn": "Corn",
        "white corn": "White Corn",
        "soybean": "Soybeans",
        "soybeans": "Soybeans",
        "wheat": "Wheat",
    }
    return aliases.get(normalized.casefold(), normalized)


def canonical_location_name(location_name: str | None) -> str | None:
    normalized = normalize_text(location_name)
    if normalized is None:
        return None
    value = re.sub(r"\s*/\s*", " / ", normalized).strip()
    # Drop trailing commodity suffixes when they are just labeling rows (e.g. "Blenheim Corn"),
    # but keep explicit crop-condition labels like "Wet Corn".
    if not re.search(r"\bwet\s+corn$", value, flags=re.IGNORECASE):
        value = re.sub(r"\s+(corn|soybeans?|wheat|barley|oats|milo)$", "", value, flags=re.IGNORECASE).strip()
    # Drop trailing ", <company>" artifacts from sheet labels (e.g. "Thamesford, GLG").
    value = re.sub(
        r",\s*(glg|g\.l\.g\.|agricharts|andersons|the andersons|hensall|snobelen|wanstead)$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()
    # Normalize "Any <X> Branch" into "<X> Branch" so filter facets do not duplicate.
    value = re.sub(r"^any\s+(.+?)\s+branch$", r"\1 Branch", value, flags=re.IGNORECASE).strip()
    # Normalize duplicate separators/spaces again after substitutions.
    value = normalize_text(value)
    if value is None:
        return None
    override = LOCATION_CANONICAL_OVERRIDES.get(value.casefold())
    return override or value


def source_scope(source_name: str | None) -> tuple[str, str | None]:
    canonical = canonical_source_name(source_name)
    if canonical is None:
        return "company", None
    lowered = canonical.casefold()
    region_name = REGION_SOURCE_LABELS.get(lowered)
    if region_name:
        return "region", region_name
    return "company", canonical
