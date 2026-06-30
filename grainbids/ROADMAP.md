# Roadmap

## Ordering Notes
- This list is dependency-ordered for execution.
- Tasks that touch the same canonicalization or dashboard surfaces should not run concurrently.
- I have kept each task narrow enough to fit in one reviewable diff.
- The persistent task specifications live under `docs/operations/tasks/`.
- Wave 1 Tasks 1-3 are complete and merged.
- Watchlist automation and alert promotion have since been implemented in the active branch; they are no longer a future roadmap gap.
- Wave 2 begins with Task 4.
- Task 8 is the trimmed billing-only split from the rejected broad billing/auth bundle and is approved for merge.
- Task 9 is the next planned production auth/session bootstrap task.

## Task Files
- [01-stabilize-docx-backfill.md](docs/operations/tasks/wave-1/01-stabilize-docx-backfill.md)
- [02-radius-bid-search.md](docs/operations/tasks/wave-1/02-radius-bid-search.md)
- [03-alert-notification-history.md](docs/operations/tasks/wave-1/03-alert-notification-history.md)
- [04-admin-mapping-editor.md](docs/operations/tasks/wave-2/04-admin-mapping-editor.md)
- [08-billing-entitlement-shell.md](docs/operations/tasks/wave-2/08-billing-entitlement-shell.md)
- [09-production-auth-session-bootstrap.md](docs/operations/tasks/wave-2/09-production-auth-session-bootstrap.md)

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
- Spec file: [docs/operations/tasks/wave-2/04-admin-mapping-editor.md](docs/operations/tasks/wave-2/04-admin-mapping-editor.md)
- Objective: Give admins a direct surface for company/location mappings and source priority maintenance.
- Exact scope: Add admin-facing UI and backing endpoints for inspecting and editing company-to-location relationships, while keeping source priority controls and canonical coverage visible on the same surface.
- Likely files: `apps/api/app/api/routes/sources.py`, `apps/api/app/api/routes/ingestion.py` if a diagnostic adapter is needed, `apps/api/tests/test_source_company_identity_diagnostics.py`, `apps/api/tests/test_sources_location_company_mapping.py`, `apps/web/app/sources/page.tsx`, `apps/web/lib/api.ts` if the page needs a small contract helper.
- Files that must not be touched: `apps/api/app/api/routes/normalized_prices.py`, `apps/web/app/dashboard/page.tsx`, `apps/web/app/bids/page.tsx`, `apps/api/app/jobs/backfill_canonical_companies.py`, `apps/api/app/jobs/backfill_canonical_locations.py`, `apps/api/app/jobs/consolidate_company_aliases.py`, `apps/api/app/services/source_file_ingestion.py`, `apps/api/app/services/upload_csv.py`, `apps/web/app/alerts/page.tsx`, `apps/web/app/watchlists/page.tsx`, `apps/web/app/quotes/page.tsx`.
- Dependencies: Task 6 request-context hardening is already merged; Task 7 cleanup is already merged; future dashboard/location-selection work should stay separate.
- Status: Completed and merged in commit `0375b14` (`Add admin location company mapping editor`).
- Acceptance criteria: Admins can inspect and update location/company mappings without leaving the product, and the source-priority and canonical-coverage views still work.
- Tests: Route tests for the mapping API plus a web build or type-check pass.
- Risk level: High.
- Can run in parallel: No with any other task that edits `apps/web/app/sources/page.tsx` or location-selection semantics.

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
- Status: completed in `d46d340` (`Harden request context access control`)
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
- Status: completed and approved in commits `9f64c4e`, `cb8eb6b`, `4fd96a5`, and `e7e22d2`; no further execution needed.
- Spec file: not yet assigned
- Objective: Remove or clearly demote compatibility surfaces that no longer represent the active product.
- Exact scope: Align the README and architecture docs with current behavior, decide whether root `/` should remain a dashboard duplicate, and keep redirect-only upload routes clearly marked as deprecated.
- Likely files: `README.md`, `docs/architecture/module-plan.md`, `docs/product/sprint-01-core-parity.md`, `apps/web/app/page.tsx`, `apps/web/app/upload/page.tsx`, `apps/web/app/uploads/page.tsx`, `app/modules/market_sources/README.md`.
- Files that must not be touched: Any files that implement the core market, ingestion, alert, or mapping flows.
- Dependencies: Do this after the functional tasks so the documentation matches the final surface. Already completed.
- Acceptance criteria: The docs no longer describe live features as scaffolds, and the compatibility routes are either intentionally preserved or explicitly deprecated.
- Tests: A docs-only review plus a minimal web sanity check.
- Risk level: Low.
- Can run in parallel: Yes, but only after the feature tasks are merged or frozen. Already completed.

## Task 8. Add a read-only billing and entitlement shell
- Spec file: [docs/operations/tasks/wave-2/08-billing-entitlement-shell.md](docs/operations/tasks/wave-2/08-billing-entitlement-shell.md)
- Objective: Give users a simple read-only billing surface that explains the current plan and upgrade path without changing auth/session or product behavior.
- Exact scope: Expose a small billing API, render a read-only billing page, and add a minimal top-nav entry point while leaving every existing product flow intact.
- Likely files: `apps/api/app/api/routes/settings.py`, `apps/api/app/services/entitlements.py`, `apps/api/tests/test_entitlements.py`, `apps/api/tests/test_settings_billing.py`, `apps/web/app/billing/page.tsx`, `apps/web/app/_components/top-nav.tsx`, `apps/web/lib/api.ts` if a tiny helper is needed.
- Files that must not be touched: `apps/api/app/core/request_context.py`, `apps/api/app/api/routes/auth.py`, `apps/api/app/core/session_auth.py`, `apps/web/middleware.ts`, `apps/web/app/login/**`, `apps/web/app/auth/**`, `apps/web/app/settings/page.tsx`, discovery routes, alert routes, watchlist routes, ingestion jobs.
- Dependencies: Task 6 request-context hardening is the baseline. Do not include auth/session rewiring in this task.
- Status: Planned.
- Acceptance criteria: A signed-in user can view plan and upgrade information in a read-only UI; no auth/session or unrelated product behavior changes are introduced.
- Tests: Endpoint tests, entitlement mapping tests, and a web type-check/build check.
- Risk level: Medium.
- Can run in parallel: No with any task that edits `apps/web/app/settings/page.tsx` or auth/session plumbing.

## Task 9. Bootstrap production auth and sessions
- Spec file: [docs/operations/tasks/wave-2/09-production-auth-session-bootstrap.md](docs/operations/tasks/wave-2/09-production-auth-session-bootstrap.md)
- Objective: Replace the production identity path with real authenticated sessions while preserving the existing local-dev header flow where it is intentionally supported.
- Exact scope: Add a minimal sign-in/session bootstrap flow, expose a current-user endpoint or equivalent bootstrap response, and make the web shell route unauthenticated users toward login without changing the working discovery, alert, watchlist, quote, or ingestion flows.
- Likely files: `apps/api/app/api/routes/auth.py`, `apps/api/app/core/session_auth.py`, `apps/api/app/core/request_context.py`, `apps/api/tests/test_auth_routes.py`, `apps/api/tests/test_request_context.py`, `apps/api/tests/test_route_authorization.py`, `apps/web/app/login/**`, `apps/web/app/auth/**`, `apps/web/middleware.ts`, `apps/web/lib/api.ts`, `apps/web/app/_components/auth-session-provider.tsx`.
- Files that must not be touched: `apps/api/app/api/routes/normalized_prices.py`, `apps/api/app/api/routes/alerts.py`, `apps/api/app/api/routes/watchlists.py`, `apps/api/app/api/routes/sources.py`, `apps/api/app/services/source_file_ingestion.py`, `apps/web/app/dashboard/page.tsx`, `apps/web/app/alerts/page.tsx`, `apps/web/app/watchlists/page.tsx`, `apps/web/app/sources/page.tsx`, `apps/web/app/quotes/page.tsx`, `apps/web/app/signals/page.tsx`.
- Dependencies: Task 6 request-context hardening is the baseline. Task 8 billing shell should stay separate and not run concurrently with this task.
- Status: Planned.
- Acceptance criteria: Production pages require authenticated identity, the web shell redirects unauthenticated users to login, local-dev header auth still works where explicitly supported, and admin-only routes still reject non-admin users.
- Tests: API config and context tests, auth route tests, protected-route tests, and a web type-check/build check.
- Risk level: High.
- Can run in parallel: No with any task that edits auth/session plumbing, `apps/web/middleware.ts`, or `apps/web/app/settings/page.tsx`.

## Conflict Summary
- Task 4 is completed; future dashboard/location-selection work should still treat `apps/web/app/sources/page.tsx` and mapping semantics as shared surfaces.
- Task 5 and Task 6 should not run concurrently because they both affect admin-facing mutation and request-context behavior.
- Task 7 is complete; any future docs maintenance should be treated as a low-risk follow-up.
- Task 8 must not run concurrently with auth/session rewiring or any task that edits `apps/web/app/settings/page.tsx`.
- Task 9 must not run concurrently with Task 8, any auth/session task, or any task that edits `apps/web/app/settings/page.tsx`.
