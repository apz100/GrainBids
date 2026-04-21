# Changelog

All notable changes to this project are documented here. This file was
generated on 2026-04-14.

## [Unreleased] - 2026-04-14
- Persist numeric helper columns as numeric types (`*_num`) in the `grain_bids` table
  so downstream queries and analysis can use numeric values directly.
- Keep legacy compatibility columns present (empty) for consumers/tests:
  `delivery_start`, `futures_symbol`, `basis_mt`.
- Make posted bids read-only in the initial release:
  - Server: `app/app.py` adds `ALLOW_POSTED_BIDS_EDIT = False` (POST returns 403).
  - UI: removed the posting form from `app/templates/index.html`.
- Fix Excel-to-DB normalization edge cases:
  - Coalesce duplicate renamed columns (e.g., multiple `delivery_end` sources) into
    one consolidated column in `app/excel_to_db.py`.
  - Add `parse_lac_html` wrapper to `lac_source.py` for test compatibility.
- Added runtime normalizer `app/normalize.py` and small test suite under `app/tests/`.

## Commits
- main 770dcc0: Persist numeric columns as numeric types (add *_num), keep
  legacy compatibility; make posted bids read-only; fix excel_to_db coalesce
