from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.location_company_seed_docx import (  # noqa: E402
    extract_single_and_yesq_seed_rows_from_docx,
    extract_single_elevator_seed_rows_from_docx,
)


def _write_minimal_docx(path: Path, document_xml: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


def test_docx_seed_extraction_keeps_only_strict_yes_and_excludes_benchmarks() -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Location / town</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Single elevator?</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Operator (if single)</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Evidence &amp; notes</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Mitchell GLG Corn</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Great Lakes Grain</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Confirmed [1]</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Ayr Corn</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes?</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Great Lakes Grain</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Uncertain</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>North Gower Corn</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Multiple / unknown</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>North Gower Grains</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Not strict yes</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>F.O.B. Farm Corn</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Benchmark</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Exclude benchmark</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Oakwood-Sunderland Co-op Corn</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Sunderland Co-operative</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Confirmed</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
    <w:p><w:r><w:t>[1]</w:t></w:r></w:p>
    <w:p><w:r><w:t>https://example.com/evidence/mitchell</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "seed.docx"
        _write_minimal_docx(docx_path, document_xml)
        rows = extract_single_elevator_seed_rows_from_docx(docx_path)

    assert len(rows) == 2
    first = rows[0]
    second = rows[1]

    assert first.raw_location_name == "Mitchell GLG Corn"
    assert first.company_name == "Great Lakes Grain"
    assert first.commodity_name == "Corn"
    assert first.source_url == "https://example.com/evidence/mitchell"
    assert first.verified is True
    assert first.confidence_score == 0.9

    assert second.raw_location_name == "Oakwood-Sunderland Co-op Corn"
    assert second.company_name == "Oakwood-Sunderland Co-op"
    assert second.commodity_name == "Corn"


def test_docx_seed_extraction_includes_only_safe_yesq_parent_matches() -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Location / town</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Single elevator?</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Operator (if single)</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Evidence &amp; notes</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Grand Valley</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes?</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Great Lakes Grain (Central Ontario FS)</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Possible parent mapping</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Dresden</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes?</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Thompsons Ltd. / The Andersons</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Rename to parent</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Varna</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes?</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Varna Grain / Huron Bay Co-operative</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Subsidiary to parent</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Palmerston</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Yes?</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Snobelen Farms or Great Lakes Grain</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Ambiguous two companies</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "seed_yesq.docx"
        _write_minimal_docx(docx_path, document_xml)
        rows = extract_single_and_yesq_seed_rows_from_docx(docx_path)

    by_location = {row.normalized_location_name: row for row in rows}
    assert "Grand Valley" in by_location
    assert "Dresden" in by_location
    assert "Varna" in by_location
    assert "Palmerston" not in by_location

    assert by_location["Grand Valley"].company_name == "Great Lakes Grain"
    assert by_location["Dresden"].company_name == "The Andersons"
    assert by_location["Varna"].company_name == "Huron Bay Co-operative"

    assert by_location["Grand Valley"].verified is False
    assert by_location["Grand Valley"].confidence_score == 0.75
    assert by_location["Grand Valley"].evidence_type == "manual_mapping_docx_yesq_parent_company"
