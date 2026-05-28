from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from app.services.market_canonicalization import (
    canonical_commodity_name,
    canonical_location_name,
    is_benchmark_location_label,
    normalize_text,
)


DEFAULT_SOURCE_URL = "https://fmn1.agricharts.com/markets/cash.php"
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass(frozen=True)
class SingleElevatorSeedRow:
    raw_location_name: str
    normalized_location_name: str
    commodity_name: str | None
    province_state: str
    country: str
    company_name: str
    facility_name: str | None
    source_url: str
    evidence_type: str
    confidence_score: float
    notes: str | None
    verified: bool


def extract_single_elevator_seed_rows_from_docx(docx_path: Path) -> list[SingleElevatorSeedRow]:
    table_rows, citation_urls = _read_docx_table_and_citations(docx_path)
    header = table_rows[0]
    location_index = _find_header_index(header, ["location / town", "location"])
    single_index = _find_header_index(header, ["single elevator", "single elevator?"])
    operator_index = _find_header_index(header, ["operator", "operator (if single)"])
    evidence_index = _find_header_index(header, ["evidence", "evidence & notes"])

    output: list[SingleElevatorSeedRow] = []
    for row in table_rows[1:]:
        if max(location_index, single_index, operator_index, evidence_index) >= len(row):
            continue
        raw_location = _clean_docx_text(normalize_text(row[location_index]))
        single_value = _clean_docx_text(normalize_text(row[single_index]))
        operator_value = _clean_docx_text(normalize_text(row[operator_index]))
        evidence_value = _clean_docx_text(normalize_text(row[evidence_index]))
        if raw_location is None or single_value is None or operator_value is None:
            continue
        row_status = _mapping_status(single_value)
        if row_status != "yes":
            continue
        if _is_benchmark_label(raw_location):
            continue
        seed_row = _build_seed_row(
            raw_location=raw_location,
            operator_value=operator_value,
            evidence_value=evidence_value,
            citation_urls=citation_urls,
            row_status=row_status,
        )
        output.append(seed_row)
    return output


def extract_single_and_yesq_seed_rows_from_docx(docx_path: Path) -> list[SingleElevatorSeedRow]:
    table_rows, citation_urls = _read_docx_table_and_citations(docx_path)
    header = table_rows[0]
    location_index = _find_header_index(header, ["location / town", "location"])
    single_index = _find_header_index(header, ["single elevator", "single elevator?"])
    operator_index = _find_header_index(header, ["operator", "operator (if single)"])
    evidence_index = _find_header_index(header, ["evidence", "evidence & notes"])

    output: list[SingleElevatorSeedRow] = []
    for row in table_rows[1:]:
        if max(location_index, single_index, operator_index, evidence_index) >= len(row):
            continue
        raw_location = _clean_docx_text(normalize_text(row[location_index]))
        single_value = _clean_docx_text(normalize_text(row[single_index]))
        operator_value = _clean_docx_text(normalize_text(row[operator_index]))
        evidence_value = _clean_docx_text(normalize_text(row[evidence_index]))
        if raw_location is None or single_value is None or operator_value is None:
            continue
        if _is_benchmark_label(raw_location):
            continue

        row_status = _mapping_status(single_value)
        if row_status == "yes":
            output.append(
                _build_seed_row(
                    raw_location=raw_location,
                    operator_value=operator_value,
                    evidence_value=evidence_value,
                    citation_urls=citation_urls,
                    row_status="yes",
                )
            )
            continue

        if row_status != "yes_question":
            continue
        canonical_yesq_company = _canonical_company_name_for_yesq(
            operator_value=operator_value,
            raw_location=raw_location,
            evidence_value=evidence_value,
        )
        if canonical_yesq_company is None:
            continue
        output.append(
            _build_seed_row(
                raw_location=raw_location,
                operator_value=operator_value,
                evidence_value=evidence_value,
                citation_urls=citation_urls,
                row_status="yes_question",
                forced_company_name=canonical_yesq_company,
            )
        )
    return output


def _read_docx_table_and_citations(docx_path: Path) -> tuple[list[list[str]], dict[str, str]]:
    if not docx_path.exists():
        raise ValueError(f"docx not found: {docx_path}")
    with zipfile.ZipFile(docx_path) as archive:
        xml_payload = archive.read("word/document.xml")
    root = ET.fromstring(xml_payload)

    table_rows = _extract_mapping_table(root)
    citations = _extract_citation_urls(root)
    return table_rows, citations


def _extract_mapping_table(root: ET.Element) -> list[list[str]]:
    for table in root.findall(".//w:tbl", WORD_NS):
        rows: list[list[str]] = []
        for tr in table.findall("./w:tr", WORD_NS):
            cells: list[str] = []
            for tc in tr.findall("./w:tc", WORD_NS):
                texts = [normalize_text(node.text) for node in tc.findall(".//w:t", WORD_NS)]
                cleaned = " ".join([value for value in texts if value]).strip()
                cleaned = _clean_docx_text(re.sub(r"\s+", " ", cleaned))
                cells.append(cleaned)
            if cells:
                rows.append(cells)
        if rows and _is_mapping_header(rows[0]):
            return rows
    raise ValueError("Could not find mapping table in DOCX")


def _extract_citation_urls(root: ET.Element) -> dict[str, str]:
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", WORD_NS):
        texts = [node.text for node in paragraph.findall(".//w:t", WORD_NS) if node.text]
        if not texts:
            continue
        value = re.sub(r"\s+", " ", " ".join(texts)).strip()
        if value:
            paragraphs.append(value)

    output: dict[str, str] = {}
    for index, line in enumerate(paragraphs):
        match = re.fullmatch(r"\[(\d+)\]", line)
        if not match:
            continue
        citation_key = match.group(1)
        next_url = ""
        for cursor in range(index + 1, min(index + 5, len(paragraphs))):
            candidate = paragraphs[cursor]
            if candidate.startswith("http://") or candidate.startswith("https://"):
                next_url = candidate
                break
        if next_url:
            output[citation_key] = _clean_docx_text(next_url)
    return output


def _is_mapping_header(header: list[str]) -> bool:
    normalized = [entry.casefold() for entry in header]
    return (
        any("location" in value for value in normalized)
        and any("single elevator" in value for value in normalized)
        and any("operator" in value for value in normalized)
    )


def _find_header_index(header: list[str], tokens: list[str]) -> int:
    normalized = [entry.casefold() for entry in header]
    for token in tokens:
        token_key = token.casefold()
        for index, value in enumerate(normalized):
            if token_key in value:
                return index
    raise ValueError(f"Required header missing. tokens={tokens}")


def _is_strict_yes(value: str) -> bool:
    cleaned = re.sub(r"\s+", " ", value.strip()).casefold()
    return cleaned == "yes"


def _mapping_status(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip()).casefold()
    if cleaned == "yes":
        return "yes"
    if cleaned == "yes?":
        return "yes_question"
    if "multiple" in cleaned or "unknown" in cleaned:
        return "multiple_unknown"
    return "other"


def _is_benchmark_label(raw_location: str) -> bool:
    key = raw_location.casefold()
    blocked_tokens = ("f.o.b", "u.s. rep", "county", "regional price", "price index")
    if any(token in key for token in blocked_tokens):
        return True
    return is_benchmark_location_label(raw_location)


def _extract_commodity_name(raw_location: str) -> str | None:
    match = re.search(r"\b(corn|soybeans?|wheat)\b", raw_location, flags=re.IGNORECASE)
    if not match:
        return None
    return _clean_docx_text(canonical_commodity_name(match.group(1)))


def _facility_name_from_location(raw_location: str) -> str:
    # Keep town-level facility labels clean while preserving parenthetical disambiguators like "(GLG)".
    return re.sub(r"\s+", " ", raw_location).strip()


def _canonical_company_name(*, operator_value: str, raw_location: str) -> str:
    text = _clean_docx_text(operator_value).casefold()
    location = _clean_docx_text(raw_location).casefold()
    if "andersons" in text or "thompsons" in text:
        return "The Andersons"
    if "great lakes grain" in text:
        return "Great Lakes Grain"
    if "london agricultural commodities" in text:
        return "London Agricultural Commodities"
    if "hensall" in text and ("hdc" in text or "co-op" in text or "co operative" in text):
        return "Hensall Co-operative"
    if "ingredion" in text:
        return "Ingredion"
    if "oakwood-sunderland" in text or "sunderland co-operative" in text or "sunderland co operative" in text:
        return "Oakwood-Sunderland Co-op"
    if "oakwood" in location and "sunderland" in location:
        return "Oakwood-Sunderland Co-op"
    if "toledo elevator" in text:
        return "Toledo Elevator"
    if "north gower grains" in text:
        return "North Gower Grains"
    if "greenfield global" in text:
        return "Greenfield Global"
    if "broadgrain" in text:
        return "BroadGrain Commodities"
    if "parrish" in text or "p&h" in text:
        return "Parrish & Heimbecker"
    if "richardson" in text:
        return "Richardson International"
    if "wilson farm grain" in text:
        return "Wilson Farm Grain"
    if "adm" in text:
        return "ADM"
    return _clean_docx_text(operator_value)


def _canonical_company_name_for_yesq(
    *,
    operator_value: str,
    raw_location: str,
    evidence_value: str | None,
) -> str | None:
    text = " ".join([operator_value, raw_location, evidence_value or ""]).casefold()

    # Explicit parent-company policy requested for Yes? rows.
    glg_parent_tokens = ("central ontario fs", "agris co-operative", "agris cooperative", "agris / great lakes grain")
    anderson_parent_tokens = ("thompsons", "the andersons", "andersons")
    huron_parent_tokens = ("huron bay co-operative", "huron bay cooperative", "varna grain")
    if any(token in text for token in glg_parent_tokens):
        return "Great Lakes Grain"
    if any(token in text for token in anderson_parent_tokens):
        return "The Andersons"
    if any(token in text for token in huron_parent_tokens):
        return "Huron Bay Co-operative"

    # For Yes? rows, skip ambiguous multi-operator strings unless they match explicit parent overrides above.
    if " or " in text or "; " in text or " and " in text:
        return None
    if "/" in text:
        return None

    candidates: set[str] = set()
    candidate_patterns = {
        "Great Lakes Grain": (
            "great lakes grain",
            "agris",
            "central ontario fs",
        ),
        "The Andersons": (
            "thompsons",
            "andersons",
        ),
        "Huron Bay Co-operative": (
            "huron bay co-operative",
            "huron bay cooperative",
            "varna grain",
        ),
        "Cargill": ("cargill",),
        "ADM": ("adm",),
        "Parrish & Heimbecker": ("parrish", "p&h"),
        "Snobelen Farms": ("snobelen",),
        "BroadGrain Commodities": ("broadgrain",),
        "Haggerty Creek Ltd.": ("haggerty creek",),
    }
    for company_name, patterns in candidate_patterns.items():
        if any(pattern in text for pattern in patterns):
            candidates.add(company_name)

    if len(candidates) == 1:
        return sorted(candidates)[0]
    return None


def _source_url_from_evidence(evidence_value: str | None, citation_urls: dict[str, str]) -> str | None:
    if evidence_value is None:
        return None
    for citation in re.findall(r"\[(\d+)\]", evidence_value):
        mapped = citation_urls.get(citation)
        if mapped:
            return _clean_docx_text(mapped)
    return None


def _build_notes(*, operator_value: str, evidence_value: str | None) -> str:
    details = f"Operator text: {operator_value}"
    if evidence_value:
        return _clean_docx_text(f"{details} | Evidence: {evidence_value}")
    return details


def _build_seed_row(
    *,
    raw_location: str,
    operator_value: str,
    evidence_value: str | None,
    citation_urls: dict[str, str],
    row_status: str,
    forced_company_name: str | None = None,
) -> SingleElevatorSeedRow:
    normalized_location = _clean_docx_text(canonical_location_name(raw_location) or raw_location)
    commodity_name = _extract_commodity_name(raw_location)
    company_name = forced_company_name or _canonical_company_name(operator_value=operator_value, raw_location=raw_location)
    facility_name = _clean_docx_text(normalize_text(_facility_name_from_location(raw_location)))
    source_url = _source_url_from_evidence(evidence_value, citation_urls) or DEFAULT_SOURCE_URL
    notes = _build_notes(operator_value=operator_value, evidence_value=evidence_value)
    if row_status == "yes_question":
        evidence_type = "manual_mapping_docx_yesq_parent_company"
        verified = False
        confidence = 0.75
    else:
        evidence_type = "manual_mapping_docx_single_elevator"
        verified = True
        confidence = 0.9
    return SingleElevatorSeedRow(
        raw_location_name=raw_location,
        normalized_location_name=normalized_location,
        commodity_name=commodity_name,
        province_state="Ontario",
        country="Canada",
        company_name=company_name,
        facility_name=facility_name,
        source_url=source_url,
        evidence_type=evidence_type,
        confidence_score=confidence,
        notes=notes,
        verified=verified,
    )


def _clean_docx_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = (
        value.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2011", "-")
        .replace("\u2010", "-")
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
    )
    return re.sub(r"\s+", " ", cleaned).strip()
