# Current State

## Scope
- `grainbids/` is the active GrainBids application.
- `archive/` is reference-only.
- The active runtime is `apps/api` plus `apps/web`.
- Legacy copies still exist under `apps/api/legacy_runtime` and `apps/api/legacy_source_ingest`, but they are not the primary runtime paths.

## What Is Implemented

### API surface
- `app/main.py` wires real routers for bids, sources, ingestion, normalized prices, alerts, quotes, watchlists, saved searches, signals, settings, and reference data.
- `app/api/routes/normalized_prices.py` is the core discovery API. It already supports summary, facets, preview, grouped preview, top movers, and origin-location/radius search.
- `app/api/routes/ingestion.py` exposes ingestion runs, SLA, diagnostics, basis-change diagnostics, and source-file reprocessing.
- `app/api/routes/sources.py` exposes source listing, seed, refresh, canonical coverage, per-company source priority management, and the location company mapping editor endpoint.
- `app/api/routes/alerts.py` exposes alert rules, recent alerts, notification logs, status updates, and rule CRUD.
- `app/api/routes/saved_searches.py` and `app/api/routes/watchlists.py` both provide CRUD plus preview endpoints; `watchlists.py` now also exposes watchlist automation inspection, enable/disable, run-now, and preview endpoints backed by a persisted automation record.
- `app/core/request_context.py` now resolves org and user identity explicitly. In production it requires `AUTH_CONTEXT_MODE=trusted_proxy`, `X-Auth-User-Id`, and an active `users.auth_user_id` match; local header fallback is only available where deliberately enabled for local development.
- `app/api/routes/quotes.py` provides quote-run history and delivered-value export generation.
- `app/api/routes/signals.py` exposes forecast rows and a health check.
- `app/api/routes/reference.py` exposes source and commodity reference lists.
- `app/api/routes/market_data.py` can list adapters, fetch live source data, and optionally persist it through the ingestion pipeline.

### Data model
- The schema already includes organizations, users, sources, commodities, price snapshots, normalized prices, ingestion runs, raw uploads, source health snapshots, companies, locations, company source priority, saved searches, notification logs, watchlists, signal forecasts, alert rules, alerts, and quote runs.
- `companies` and `locations` are real tables, not planning stubs.
- `locations` already has `company_id`, `postal_code`, `latitude`, and `longitude` columns.
- `normalized_prices` already has `company_id`, `location_id`, canonicality flags, basis/cash/futures change columns, and basis carry metadata.

### Ingestion and canonicalization
- The active ingestion flow is `source file -> upload/persist -> normalized_prices -> canonical resolver -> alerts`.
- `app/services/source_file_ingestion.py` handles file ingestion, workbook parsing, commodity resolution, location/company resolution, dedupe, quality metrics, and alert evaluation.
- `app/services/canonical_resolver.py` resolves canonical rows using company priority, quality scoring, and source preference.
- `app/services/price_comparison.py` computes historical cash/basis changes and basis carry behavior.
- `app/services/source_orchestration.py` manages source refresh, polling, SLA summaries, source health, and file-source logical rows.
- `app/services/source_health.py` records per-source health snapshots and confidence scores.
- `app/services/alert_evaluator.py` evaluates alert rules against snapshots and deduplicates open alerts.
- `app/services/alert_notifier.py` can send email notifications and writes `notification_logs` rows for sent, skipped, and failed deliveries.
- `app/services/watchlist_automation.py` links active watchlists to saved-search-backed alert rules, runs daily digest notifications, and records digest history in `notification_logs`.
- The DOCX benchmark-label helper contract and source-company backfill alias resolution defects from the audit have been fixed in committed Task 1 changes.
- Radius search and notification-history visibility were added in approved Wave 1 Task 2 and Task 3 changes.
- Production-grade request-context hardening and admin-gated mutation enforcement were added in Task 6 and merged on top of Wave 1.

### Web surface
- `app/page.tsx` renders a lightweight product entry page and links into the active market dashboard at `/bids`; `/dashboard` remains the underlying dashboard route.
- `app/dashboard/page.tsx` is a real table-first market UI with commodity tabs, location/company/region filters, date and sort filters, origin/radius search, summary stats, live preview rows, grouped monthly preview, top movers, watchlist creation, alert creation, and an open-alerts panel.
- `app/bids/page.tsx` reuses the dashboard.
- `app/sources/page.tsx` is a real admin source-management page with SLA cards, canonical coverage, source priority controls, company/location mapping editor controls, ingestion runs, alert triage, and manual ingestion triggers.
- `app/alerts/page.tsx` is a real alert management page with rule CRUD, alert filters, alert acknowledgement/resolution, and notification history visibility.
- `app/watchlists/page.tsx` is a real watchlist and saved-search CRUD page with previews, automation status, linked alert state, and digest history.
- `app/quotes/page.tsx` is a real delivered-value export page.
- `app/signals/page.tsx` is a real forecast viewer, albeit isolated from the core market flow.
- `app/settings/page.tsx` is still a scaffolded admin shell.
- `app/upload/page.tsx` and `app/uploads/page.tsx` now redirect to `/sources`.
- `app/_components/top-nav.tsx` shows the main product routes and hides admin routes unless the user role is admin/owner.

### Operational scripts
- `infra/scripts/run-api.ps1` starts the FastAPI app and bootstraps the venv if needed.
- `infra/scripts/run-web.ps1` starts Next.js and bootstraps npm deps if needed.
- `infra/scripts/run-all.ps1` starts both services and can restart existing listeners.
- `infra/scripts/run-daily-ingestion.ps1` runs the daily ingestion job and writes `.runlogs/daily-ingestion-*.log`.
- `infra/scripts/run-watchlist-automation.ps1` runs the daily watchlist automation digest job and writes `.runlogs/watchlist-automation-*.log`.
- `infra/scripts/run-fetch-and-ingest.ps1` runs source fetchers, optionally uploads files to Supabase, and can trigger cloud ingestion.
- `infra/scripts/run-source-poller.ps1` runs the polling job.
- `infra/scripts/reprocess-latest-file-source.ps1` reprocesses the latest file-backed snapshot.
- `infra/scripts/db-migrate.ps1` runs Alembic migrations.
- The agent queue/worktree scripts are present and documented, but they are operational scaffolding rather than product features.

## Stale Or Thin Areas
- `app/api/routes/bids.py` is only module metadata; the real data lives in `normalized_prices`.
- `app/api/routes/settings.py` is only a module stub.
- `app/api/routes/signals.py` is real, but it is still a standalone feature island.
- `app/modules/market_sources` is a compatibility shim that points callers to `app/platform/market_data/sources`.
- `app/modules/imports` still contains legacy normalization helpers.
- `app/page.tsx` is now a lightweight entry page; the duplicate dashboard experience no longer appears on `/`.
- `docs/architecture/module-plan.md` and `docs/product/sprint-01-core-parity.md` have been synchronized with the active product posture; `sprint-01-core-parity.md` remains a historical planning record, not a live-state source of truth.

## Verified Breaks
- No verified backend breaks remain from the Wave 1 audit tasks or Task 6.
- The Task 6 worker verification reported a successful `npm run build` in `apps/web` after the access-control changes.

## Verification Run
- `pytest -q tests/test_location_company_seed_docx.py` passed with 2 tests.
- `pytest -q tests/test_backfill_source_company_identity.py` passed with 6 tests.
- `pytest -q tests/test_market_canonicalization.py` passed with 8 tests.
- `pytest -q tests/test_normalized_price_filters.py tests/test_normalized_price_query_helpers.py` passed with 16 tests and 1 warning.
- `pytest -q tests/test_alert_evaluator.py tests/test_alert_notification_logs.py` passed with 7 tests and 1 warning.
- `pytest -q tests/test_config_runtime.py tests/test_request_context.py tests/test_route_authorization.py tests/test_alert_notification_logs.py` passed with 14 tests and 1 warning.
- `pytest -q tests/test_source_company_identity_diagnostics.py tests/test_sources_location_company_mapping.py` passed with 7 tests and 2 warnings.
- `pytest -q tests/test_watchlist_automation.py tests/test_alert_evaluator.py tests/test_alert_notification_logs.py tests/test_route_authorization.py` passed with 13 tests and 1 warning.
- `pytest -q` in `apps/api` passed in the worker reports for Wave 1 tasks, with totals ranging from 99 to 101 tests and 1 warning.
- `pytest -q` in `apps/api` passed locally after the watchlist automation implementation with 119 tests and 1 warning.
- `pytest -q` in `apps/api` passed in the Wave 2 Task 4 worker report with 117 tests and 2 warnings.
- `npm run build` in `apps/web` passed in the Task 6 worker verification after the request-context changes.
- `npx tsc --noEmit --pretty false` passed in the Wave 2 Task 4 worker report using the local TypeScript binary.
- `npm run build` in `apps/web` passed in the Wave 2 Task 4 worker report after the worker reran it with escalation.
- `npx tsc --noEmit --pretty false` passed locally after the watchlist automation UI changes.
- `npm run build` in `apps/web` still fails locally with `spawn EPERM` from Next.js worker startup; the failure appears environment-specific because typecheck succeeds.
