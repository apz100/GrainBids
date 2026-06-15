# Task 1: Stabilize DOCX Benchmark Filtering and Source-Company Backfill

## Branch Slug
`codex/stabilize-docx-backfill`

## Objective
Fix the two verified backend defects from the repository audit and restore a fully green API test run.

## Business Value
- Unblocks CI and local verification.
- Restores the DOCX benchmark seed-extraction path used by the location/company seed flow.
- Fixes a data-integrity bug in source-derived company backfill resolution.

## Background
The audit verified two concrete failures in the active backend:
- `apps/api/tests/test_location_company_seed_docx.py` fails during collection because `location_company_seed_docx.py` imports `is_benchmark_location_label` from `market_canonicalization.py`, but that symbol is missing there.
- `apps/api/tests/test_backfill_source_company_identity.py` fails two assertions because `_desired_company_id_for_row(...)` does not resolve GLG-style aliases through the trusted-company lookup.

The rest of the API suite passes when those two broken areas are ignored, so this is a narrow stabilization task rather than a broader refactor.

## Current Repository Context
- The active application is `grainbids/`, not `archive/`.
- The backend API is real and already covers discovery, ingestion, alerts, saved searches, watchlists, quotes, signals, and source management.
- Canonicalization helpers are shared across multiple backend surfaces, so changes here need to stay minimal and well-tested.

## Exact Implementation Scope
- Restore the benchmark-label helper contract used by `apps/api/app/services/location_company_seed_docx.py`.
- Fix `_desired_company_id_for_row(...)` in `apps/api/app/jobs/backfill_source_company_identity.py` so source-name aliases and trusted-company lookups resolve consistently.
- Update or add the smallest possible set of tests to prove both defects are fixed.

## Out-of-Scope Items
- No web UI changes.
- No Alembic migration.
- No route additions or route refactors.
- No ingestion pipeline redesign.
- No unrelated canonicalization cleanup.
- No changes to alerting, watchlists, quotes, or signals.

## Dependencies
- None.

## Likely Files to Change
- `apps/api/app/services/market_canonicalization.py`
- `apps/api/app/services/location_company_seed_docx.py`
- `apps/api/app/jobs/backfill_source_company_identity.py`
- `apps/api/tests/test_location_company_seed_docx.py`
- `apps/api/tests/test_backfill_source_company_identity.py`
- `apps/api/tests/test_market_canonicalization.py` if the helper contract needs test coverage there

## Files That Must Not Change
- `apps/web/**`
- `apps/api/alembic/**`
- `apps/api/app/api/routes/**`
- `infra/scripts/**`
- `docs/**` unless a test note is strictly necessary

## Shared Contracts
- `market_canonicalization.py` helper semantics are shared by DOCX seed extraction and backfill identity resolution.
- The source-company backfill job is the active contract for rewriting company IDs on existing normalized rows.

## Database Migration Requirements
- None.

## API Contract Changes
- None.

## Frontend Contract Changes
- None.

## Acceptance Criteria
- `pytest -q` in `apps/api` passes.
- The DOCX seed path imports cleanly.
- The backfill tests cover the alias/trusted-company cases and pass.

## Tests
- `pytest -q tests/test_location_company_seed_docx.py tests/test_backfill_source_company_identity.py tests/test_market_canonicalization.py`
- `pytest -q`

## Exact Test Commands
- `pytest -q tests/test_location_company_seed_docx.py tests/test_backfill_source_company_identity.py tests/test_market_canonicalization.py`
- `pytest -q`

## Risks
- Low to medium.
- The main risk is accidentally widening canonicalization semantics beyond the verified bug fixes.

## Reviewer Checklist
- Confirm the DOCX helper contract is restored cleanly.
- Confirm `_desired_company_id_for_row(...)` now resolves GLG-style aliases and trusted-company matches correctly.
- Confirm the tests prove both verified failures are fixed.
- Confirm no unrelated ingestion or canonicalization refactor slipped in.

## Concurrency Restrictions
- Do not run concurrently with any task that changes the same canonicalization helper surface.
- This task should merge before product tasks that depend on a clean backend baseline.
