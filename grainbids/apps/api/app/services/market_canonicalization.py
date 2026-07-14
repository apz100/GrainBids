from __future__ import annotations

import re


NULL_LIKE = {"nan", "none", "null", "na", "n/a", "-"}
REGION_SOURCE_LABELS = {
    "eastern ontario cash bids": "Eastern Ontario",
    "ontario cash bids": "Ontario",
}
REGION_CANONICAL_SOURCE_LABELS = {
    "eastern ontario": ("Eastern Ontario Cash Bids",),
    "ontario": ("Ontario Cash Bids",),
}
LOCATION_CANONICAL_OVERRIDES = {
    # Known deterministic typo/variant cleanups
    "starffordville": "Straffordville",
    "staffordville": "Straffordville",
    # User-approved location label canonical display
    "prescott transfer": "Prescott",
    "prescott (transfer)": "Prescott",
    "ingredion cardinal": "Cardinal",
    "johnstown ethanol": "Johnstown",
    "johnstown (ethanol)": "Johnstown",
    "embrun elevator": "Embrun",
    "embrun co-op": "Embrun",
    "embrun coop": "Embrun",
    # Source-emitted variants that should map to one market location label
    "toledo": "Toledo Elevator",
    "toledo corn": "Toledo Elevator",
    "toledo soybeans": "Toledo Elevator",
}
_BENCHMARK_STRONG_PHRASES = (
    "benchmark",
    "regional price",
    "price index",
)
_BENCHMARK_WEAK_WORDS = {"avg", "average", "county", "cty"}
_BENCHMARK_PHYSICAL_HINTS = {
    "branch",
    "co op",
    "cooperative",
    "company",
    "coop",
    "elevator",
    "farm",
    "farms",
    "feed",
    "grain",
    "location",
    "mill",
    "road",
    "route",
    "street",
    "town road",
    "plant",
    "terminal",
    "trail",
    "town",
    "township",
    "transfer",
    "village",
    "way",
    "drive",
    "lane",
    "highway",
    "avenue",
    "boulevard",
    "court",
    "place",
}
_BENCHMARK_FOB_PATTERN = re.compile(r"\bf[\s.]*o[\s.]*b\b", flags=re.IGNORECASE)
_BENCHMARK_US_REP_PATTERN = re.compile(r"\b(?:u[\s.]*s|us)[\s.]*rep\b", flags=re.IGNORECASE)


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
        # Company/source aliases collapsed to one user-facing company label.
        "glg": "Great Lakes Grain",
        "g.l.g.": "Great Lakes Grain",
        "great lakes grain": "Great Lakes Grain",
        "agris": "Great Lakes Grain",
        "agris co-operative": "Great Lakes Grain",
        "agris cooperative": "Great Lakes Grain",
        "central ontario fs": "Great Lakes Grain",
        "lac": "London Agricultural Commodities",
        "london ag commodities": "London Agricultural Commodities",
        "london agricultural commodities": "London Agricultural Commodities",
        "hensall": "Hensall Co-operative",
        "hensall hdc": "Hensall Co-operative",
        "hdc": "Hensall Co-operative",
        "hensall co-op": "Hensall Co-operative",
        "hensall co-operative": "Hensall Co-operative",
        "hensall cooperative": "Hensall Co-operative",
        "snobelen": "Snobelen Farms",
        "snobelen farms": "Snobelen Farms",
        "port of prescott grain terminal": "Port of Prescott",
        "port of prescott": "Port of Prescott",
        "agricharts": "Agricharts",
        "andersons": "The Andersons",
        "the andersons": "The Andersons",
        "thompsons": "The Andersons",
        "thompsons ltd": "The Andersons",
        "thompsons limited": "The Andersons",
        "wanstead": "Wanstead",
        "eastern ontario cash bids": "Eastern Ontario Cash Bids",
        "eastern ontario daily file": "Eastern Ontario Cash Bids",
        "ontario cash bids": "Ontario Cash Bids",
        "ontario daily file": "Ontario Cash Bids",
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


def is_benchmark_location_label(location_name: str | None) -> bool:
    normalized = normalize_text(location_name)
    if normalized is None:
        return False
    lowered = re.sub(r"[^0-9A-Za-z]+", " ", normalized).casefold()
    lowered = re.sub(r"\s+", " ", lowered).strip()
    if not lowered:
        return False
    if any(phrase in lowered for phrase in _BENCHMARK_STRONG_PHRASES):
        return True
    if _BENCHMARK_FOB_PATTERN.search(lowered) or _BENCHMARK_US_REP_PATTERN.search(lowered):
        return True

    tokens = lowered.split()
    if not tokens:
        return False
    if any(token in _BENCHMARK_WEAK_WORDS for token in tokens):
        if any(hint in lowered for hint in _BENCHMARK_PHYSICAL_HINTS):
            return False
        return True
    if tokens == ["county"] or tokens == ["cty"]:
        return True
    return False


def source_scope(source_name: str | None) -> tuple[str, str | None]:
    canonical = canonical_source_name(source_name)
    if canonical is None:
        return "company", None
    lowered = canonical.casefold()
    region_name = REGION_SOURCE_LABELS.get(lowered)
    if region_name:
        return "region", region_name
    return "company", canonical


def region_source_names(region_name: str | None) -> tuple[str, ...]:
    normalized = normalize_text(region_name)
    if normalized is None:
        return ()
    return REGION_CANONICAL_SOURCE_LABELS.get(normalized.casefold(), ())
