# Current State

## Scope
- `grainbids/` is the active GrainBids application.
- `archive/` is reference-only.
- The active runtime is `apps/api` plus `apps/web`.
- Legacy copies still exist under `apps/api/legacy_runtime` and `apps/api/legacy_source_ingest`, but they are not the primary runtime paths.

## What Is Implemented

### API surface
- `app/main.py` wires real routers for bids, sources, ingestion, normalized prices, alerts, quotes, watchlists, saved searches, signals, settings, and reference data.
- `app/api/routes/normalized_prices.py` is the core discovery API. It already supports summary, facets, preview, grouped preview, and top movers.
- `app/api/routes/ingestion.py` exposes ingestion runs, SLA, diagnostics, basis-change diagnostics, and source-file reprocessing.
- `app/api/routes/sources.py` exposes source listing, seed, refresh, canonical coverage, and per-company source priority management.
- `app/api/routes/alerts.py` exposes alert rules, recent alerts, status updates, and rule CRUD.
- `app/api/routes/saved_searches.py` and `app/api/routes/watchlists.py` both provide CRUD plus preview endpoints.
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

### Web surface
- `app/page.tsx` renders the market dashboard shell and then mounts the dashboard page.
- `app/dashboard/page.tsx` is a real table-first market UI with commodity tabs, location/company/region filters, date and sort filters, summary stats, live preview rows, grouped monthly preview, top movers, watchlist creation, alert creation, and an open-alerts panel.
- `app/bids/page.tsx` reuses the dashboard.
- `app/sources/page.tsx` is a real admin source-management page with SLA cards, canonical coverage, source priority controls, ingestion runs, alert triage, and manual ingestion triggers.
- `app/alerts/page.tsx` is a real alert management page with rule CRUD, alert filters, and alert acknowledgement/resolution.
- `app/watchlists/page.tsx` is a real watchlist and saved-search CRUD page with previews.
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
- `app/page.tsx` renders the dashboard again below the landing content, which duplicates the `/dashboard` experience.
- The docs in `docs/architecture/module-plan.md` and `docs/product/sprint-01-core-parity.md` are not reliable indicators of current implementation; they describe some features as scaffolds even though the code now exists.

## Verified Breaks
- Full backend test collection fails because `app/services/location_company_seed_docx.py` imports `is_benchmark_location_label` from `app/services/market_canonicalization.py`, but that symbol is not defined there.
- After ignoring that file, `tests/test_backfill_source_company_identity.py` still fails two assertions around `_desired_company_id_for_row`.
- With those two suites ignored, the rest of the API tests pass.
- `npm run build` in `apps/web` failed on this machine with `spawn EPERM` from Next worker startup, so the web production build is not currently verified in this environment.

## Verification Run
- `pytest -q` in `apps/api` stopped at collection with the missing `is_benchmark_location_label` import.
- `pytest -q --ignore=tests/test_location_company_seed_docx.py` in `apps/api` produced 2 failures in `tests/test_backfill_source_company_identity.py`.
- `pytest -q --ignore=tests/test_location_company_seed_docx.py --ignore=tests/test_backfill_source_company_identity.py` passed 90 tests.
- `npm run build` in `apps/web` failed with `spawn EPERM`.

