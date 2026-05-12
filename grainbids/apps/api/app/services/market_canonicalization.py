from __future__ import annotations

import re


NULL_LIKE = {"nan", "none", "null", "na", "n/a", "-"}


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
    # Normalize "Any <X> Branch" into "<X> Branch" so filter facets do not duplicate.
    value = re.sub(r"^any\s+(.+?)\s+branch$", r"\1 Branch", value, flags=re.IGNORECASE).strip()
    # Normalize duplicate separators/spaces again after substitutions.
    return normalize_text(value)


def source_scope(source_name: str | None) -> tuple[str, str | None]:
    canonical = canonical_source_name(source_name)
    if canonical is None:
        return "company", None
    lowered = canonical.casefold()
    if "ontario" in lowered and ("cash bids" in lowered or "daily file" in lowered):
        region_name = "Eastern Ontario" if "eastern" in lowered else "Ontario"
        return "region", region_name
    return "company", canonical
