from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.location_company_seed_docx import (
    extract_single_and_yesq_seed_rows_from_docx,
    extract_single_elevator_seed_rows_from_docx,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract DOCX location/company mappings into seed CSV.")
    parser.add_argument("--docx-path", required=True, help="Path to .docx source file")
    parser.add_argument("--output-csv", required=True, help="Path to output CSV")
    parser.add_argument(
        "--include-yesq-parent-matches",
        action="store_true",
        help="Include Yes? rows only when they resolve to a single canonical parent-company mapping.",
    )
    args = parser.parse_args()

    source_path = Path(args.docx_path).expanduser().resolve()
    output_path = Path(args.output_csv).expanduser().resolve()
    if args.include_yesq_parent_matches:
        rows = extract_single_and_yesq_seed_rows_from_docx(source_path)
    else:
        rows = extract_single_elevator_seed_rows_from_docx(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "raw_location_name",
        "normalized_location_name",
        "commodity_name",
        "province_state",
        "country",
        "company_name",
        "facility_name",
        "source_url",
        "evidence_type",
        "confidence_score",
        "notes",
        "verified",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "raw_location_name": row.raw_location_name,
                    "normalized_location_name": row.normalized_location_name,
                    "commodity_name": row.commodity_name or "",
                    "province_state": row.province_state,
                    "country": row.country,
                    "company_name": row.company_name,
                    "facility_name": row.facility_name or "",
                    "source_url": row.source_url,
                    "evidence_type": row.evidence_type,
                    "confidence_score": f"{row.confidence_score:.3f}",
                    "notes": row.notes or "",
                    "verified": "true" if row.verified else "false",
                }
            )

    print(f"source={source_path}")
    print(f"output={output_path}")
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
