# GrainBids Module Plan

GrainBids is the umbrella product. Product modules consume shared platform services instead of owning duplicated ingestion or pricing logic.

## Frontend Routes
- `app/page.tsx`: lightweight product entry page; it links into the active market surface and no longer duplicates dashboard content
- `app/bids`: active table-first market dashboard backed by normalized-price APIs
- `app/dashboard`: dashboard implementation route reused by `/bids`
- `app/sources`: admin source management, source health, canonical coverage, source priority controls, manual ingestion triggers, ingestion runs, and alert triage
- `app/alerts`: active alert-rule CRUD, alert triage, and notification-history visibility
- `app/quotes`: active delivered-value export workflow
- `app/watchlists`: active saved-search and watchlist CRUD with previews
- `app/signals`: active forecast viewer, still isolated from the core market workflow
- `app/settings`: scaffolded admin shell for organization defaults and access controls
- `app/upload` and `app/uploads`: deprecated compatibility redirects to `/sources`

## Backend Routes
- `api/routes/normalized_prices.py`: primary market-discovery API for summary, facets, preview, grouped preview, top movers, and origin/radius search
- `api/routes/bids.py`: compatibility metadata only; live bid data belongs to normalized-price routes
- `api/routes/sources.py`: active source listing, seed, refresh, canonical coverage, and company source priority management
- `api/routes/ingestion.py`: source-file ingestion trigger, run history, SLA, diagnostics, basis-change diagnostics, and reprocessing
- `api/routes/alerts.py`: active alert rules, recent alerts, notification logs, status updates, and rule CRUD
- `api/routes/quotes.py`: active quote-run history and delivered-value export generation
- `api/routes/watchlists.py`: active watchlist CRUD and preview endpoints
- `api/routes/saved_searches.py`: active saved-search CRUD and preview endpoints
- `api/routes/signals.py`: active signal forecast rows and health check
- `api/routes/reference.py`: source and commodity reference data
- `api/routes/settings.py`: compatibility metadata only; settings UI is not a full productized admin system yet

## Shared Platform Services
- `app/platform/market_data`: shared grain-price fetching layer
- `app/services/market_data.py`: source refresh orchestration
- `app/services/source_file_ingestion.py`: CSV/XLSX file ingestion and run metadata
- `app/services/upload_csv.py`: reusable normalization and persistence helpers
- `app/services/canonical_resolver.py`: canonical row selection by source priority and quality scoring
- `app/services/alert_evaluator.py` and `app/services/alert_notifier.py`: alert evaluation plus durable notification status

## Compatibility Boundaries
- `app/modules/market_sources` is a deprecated import shim for callers that have not moved to `app.platform.market_data.sources`.
- `app/modules/imports` contains legacy normalization helpers retained for migration support.
- Legacy runtime copies under `apps/api/legacy_runtime` and `apps/api/legacy_source_ingest` are reference-only.

## Current Product Focus
The active path is:

`source file -> upload/persist -> normalized_prices -> canonical resolver -> alerts -> market dashboard`
