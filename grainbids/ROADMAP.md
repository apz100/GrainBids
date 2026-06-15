# Roadmap

## Ordering Notes
- This list is dependency-ordered for execution.
- Tasks that touch the same canonicalization or dashboard surfaces should not run concurrently.
- I have kept each task narrow enough to fit in one reviewable diff.
- The persistent task specifications live under `docs/operations/tasks/wave-1/`.
- Wave 1 Tasks 1-3 are complete and merged.

## Task Files
- [01-stabilize-docx-backfill.md](docs/operations/tasks/wave-1/01-stabilize-docx-backfill.md)
- [02-radius-bid-search.md](docs/operations/tasks/wave-1/02-radius-bid-search.md)
- [03-alert-notification-history.md](docs/operations/tasks/wave-1/03-alert-notification-history.md)

## Task 1. Restore DOCX benchmark filtering
- Spec file: [docs/operations/tasks/wave-1/01-stabilize-docx-backfill.md](docs/operations/tasks/wave-1/01-stabilize-docx-backfill.md)
- Objective: Fix the DOCX seed-extraction path so the benchmark-filtering helper exists and test collection succeeds.
- Exact scope: Add the missing benchmark-label helper or refactor the importer to use the active canonicalization API, then make the DOCX seed extractor and its tests pass.
- Likely files: `apps/api/app/services/market_canonicalization.py`, `apps/api/app/services/location_company_seed_docx.py`, `apps/api/tests/test_location_company_seed_docx.py`, `apps/api/tests/test_market_canonicalization.py`.
- Files that must not be touched: `apps/web/**`, Alembic migrations, ingestion routes, alert routes.
- Dependencies: None.
- Status: Completed and approved in commit `1c95a3a`; planning state recorded in `59859a6`.
- Acceptance criteria: `pytest -q tests/test_location_company_seed_docx.py tests/test_market_canonicalization.py` and `pytest -q tests/test_backfill_source_company_identity.py` pass; full API suite passes.
- Tests: `pytest -q tests/test_location_company_seed_docx.py`, `pytest -q tests/test_backfill_source_company_identity.py`, `pytest -q tests/test_market_canonicalization.py`, and `pytest -q`.
- Risk level: Low.
- Can run in parallel: Yes, but not with Task 2 if both change shared canonicalization semantics.

## Task 2. Fix source-company backfill resolution
- Spec file: [docs/operations/tasks/wave-1/01-stabilize-docx-backfill.md](docs/operations/tasks/wave-1/01-stabilize-docx-backfill.md)
- Objective: Make source-derived company backfills resolve GLG-style aliases and existing trusted companies correctly.
- Exact scope: Repair `_desired_company_id_for_row`, any lookup-map construction that feeds it, and the matching tests so the job rewrites company IDs deterministically.
- Likely files: `apps/api/app/jobs/backfill_source_company_identity.py`, `apps/api/tests/test_backfill_source_company_identity.py`.
- Files that must not be touched: `apps/api/app/api/routes/*`, `apps/web/**`, `apps/api/app/services/source_file_ingestion.py`.
- Dependencies: Task 1 if the canonicalization helper surface is changed there.
- Status: Completed and approved in commit `1c95a3a`; merged into `main` in merge commit `bc0dbfc0ee73456d79983bb28f30990ef0a65b13`.
- Acceptance criteria: `pytest -q tests/test_backfill_source_company_identity.py` passes.
- Tests: The backfill unit test file plus the relevant helper tests if lookup semantics move.
- Risk level: Medium.
- Can run in parallel: Yes, unless Task 1 edits the same canonicalization file.

## Task 3. Add radius search to market discovery
- Spec file: [docs/operations/tasks/wave-1/02-radius-bid-search.md](docs/operations/tasks/wave-1/02-radius-bid-search.md)
- Objective: Support location-radius search in the bid discovery flow.
- Exact scope: Add API support for an origin location plus radius filter, use the existing `locations.latitude` and `locations.longitude` fields, and expose the control in the dashboard filter bar.
- Likely files: `apps/api/app/api/routes/normalized_prices.py`, `apps/api/app/models/location.py` if model helpers are needed, `apps/web/app/dashboard/page.tsx`, `apps/web/lib/api.ts` if query helpers need to change, `apps/api/tests/test_normalized_price_filters.py`, `apps/api/tests/test_normalized_price_query_helpers.py`.
- Files that must not be touched: Alert evaluator, watchlist CRUD, quote export, ingestion jobs.
- Dependencies: Task 1 and Task 2 should be stabilized first so location/company identity stays consistent.
- Status: Completed and approved in commit `1d82231788b763c01333d7cd5b2bb87b2cbd5666`; merged into `main` in merge commit `bc0dbfc0ee73456d79983bb28f30990ef0a65b13`.
- Acceptance criteria: The API can filter by origin + radius, the dashboard can submit the new filter, and the results remain deterministic when coordinates are missing.
- Tests: Existing normalized-price filter tests plus new radius-search coverage and a web build check if the environment allows it.
- Risk level: Medium to high.
- Can run in parallel: No with Task 4 because both will touch the dashboard filter surface.

## Task 4. Build a real admin mapping editor
- Spec file: not yet assigned
- Objective: Give admins a direct surface for company/location mappings and source priority maintenance.
- Exact scope: Add UI and backing endpoints for inspecting and editing company-to-location relationships, while keeping source priority controls and canonical coverage visible.
- Likely files: `apps/api/app/api/routes/sources.py` or a new mapping route module, `apps/api/app/jobs/backfill_canonical_companies.py`, `apps/api/app/jobs/backfill_canonical_locations.py`, `apps/web/app/sources/page.tsx`, possibly a new admin page under `apps/web/app/settings/`.
- Files that must not be touched: Normalized-price query helpers, quote export, alert evaluation logic.
- Dependencies: Task 2 should be stable first; Task 3 should already define the location selector semantics if the editor reuses it.
- Acceptance criteria: Admins can inspect and save mapping changes without leaving the product, and the source-priority views still work.
- Tests: Route tests for the mapping API plus a web build or type-check pass.
- Risk level: High.
- Can run in parallel: No with Task 3 because both touch the dashboard/admin location-selection surface.

## Task 5. Add notification history and delivery status visibility
- Spec file: [docs/operations/tasks/wave-1/03-alert-notification-history.md](docs/operations/tasks/wave-1/03-alert-notification-history.md)
- Status: Completed and approved in commit `dd38bdce0de3ada37fecfa65eca7db376db4a6fe`; already present on `main`.
- Objective: Make alert delivery outcomes visible and durable.
- Exact scope: Expose `notification_logs` through the API, surface delivery status in the UI, and keep the notifier writing a visible record for sent, skipped, and failed deliveries.
- Likely files: `apps/api/app/services/alert_notifier.py`, `apps/api/app/api/routes/alerts.py` or a dedicated notification route, `apps/api/app/models/notification_log.py`, `apps/web/app/alerts/page.tsx` or `apps/web/app/dashboard/open-alerts-panel.tsx`.
- Files that must not be touched: Radius search logic, mapping backfills, quote export.
- Dependencies: Alert CRUD and rule evaluation should remain stable.
- Acceptance criteria: A user can see notification attempts and their statuses after alerts are evaluated.
- Tests: Unit tests around notifier logging plus route tests for the notification-log API.
- Risk level: Medium.
- Can run in parallel: Not with Task 6 if the request-context or admin-gating model changes the alert UI.

## Task 6. Harden org/user access control
- Spec file: not yet assigned
- Objective: Replace the current implicit header-driven access model with a real production-grade request-context strategy.
- Exact scope: Make org and user identity explicit in production, keep local dev support only where it is intentional, and tighten admin gating on mutation routes.
- Likely files: `apps/api/app/core/config.py`, `apps/api/app/core/request_context.py`, `apps/web/lib/api.ts`, any page components that assume headers are always sufficient.
- Files that must not be touched: Normalized-price search semantics, ingestion pipelines, historical comparison logic.
- Dependencies: None functionally, but it should land before any production-facing admin editor is finalized.
- Acceptance criteria: Production cannot fall back to implicit org selection, admin-only mutations are consistently rejected without the required context, and local-dev fallback is still deliberate.
- Tests: `tests/test_config_runtime.py` plus new request-context and route authorization tests.
- Risk level: High.
- Can run in parallel: No with Task 5 because both affect admin-facing request context and mutation flows.

## Task 7. Clean up obsolete routes and stale docs
- Spec file: not yet assigned
- Objective: Remove or clearly demote compatibility surfaces that no longer represent the active product.
- Exact scope: Align the README and architecture docs with current behavior, decide whether root `/` should remain a dashboard duplicate, and keep redirect-only upload routes clearly marked as deprecated.
- Likely files: `README.md`, `docs/architecture/module-plan.md`, `docs/product/sprint-01-core-parity.md`, `apps/web/app/page.tsx`, `apps/web/app/upload/page.tsx`, `apps/web/app/uploads/page.tsx`, `app/modules/market_sources/README.md`.
- Files that must not be touched: Any files that implement the core market, ingestion, alert, or mapping flows.
- Dependencies: Do this after the functional tasks so the documentation matches the final surface.
- Acceptance criteria: The docs no longer describe live features as scaffolds, and the compatibility routes are either intentionally preserved or explicitly deprecated.
- Tests: A docs-only review plus a minimal web sanity check.
- Risk level: Low.
- Can run in parallel: Yes, but only after the feature tasks are merged or frozen.

## Conflict Summary
- Task 4 remains the main known conflict surface with future dashboard/location-selection work.
- Task 5 and Task 6 should not run concurrently because they both affect admin-facing mutation and request-context behavior.
- Task 7 should wait until the product-facing tasks are settled, otherwise the docs will go stale immediately.
