# Product Gaps

## Implemented or Largely Implemented
- Farmbucks-style bid discovery exists in the dashboard and normalized-price API.
- Company and elevator canonicalization exists in schema, resolver, backfill jobs, and source-priority controls.
- Commodity and delivery-period filters exist in the API and dashboard.
- Historical bid deltas exist through basis and cash/futures change columns plus carry-policy logic.
- Ingestion monitoring, run history, source freshness, and data-quality visibility are present.
- Saved searches and watchlists exist with CRUD and preview flows.
- Alerts exist with rule CRUD, recent-alert views, acknowledgement, resolution, and email notification hooks.
- Quote export exists.

## Partial
- The dashboard is responsive in CSS terms, but it is still a dense desktop-first table UI.
- The sources page exposes meaningful admin controls, but most mapping work is read-only or priority-based rather than a true editor for companies, locations, and source relationships.
- Signals exists as a product area, but it is not integrated into the core discovery workflow.
- Alert delivery is logged, but only through the SMTP path in `alert_notifier.py`; there is no visible notification-log UI.
- `settings` is still a shell, so organization defaults, billing, and access controls are not productized in the UI.
- Root `/` duplicates the dashboard content instead of acting as a distinct landing experience.

## Missing
- Radius search is not implemented as a geospatial filter. The `locations` table already has latitude and longitude, but the active search API does not use them.
- There is no dedicated company/location mapping editor in the web UI.
- There is no user-facing notification history page for `notification_logs`.
- Watchlists are CRUD + preview only; there is no scheduled watchlist execution/alert loop exposed to users.
- Price alerts exist, but the provider abstraction is still effectively email-only.
- Access control is header-based and implicit. There is no real auth/session layer in the active app.
- The location/company DOCX seed extraction path is currently broken because of the missing benchmark-label helper import.
- Backfill logic for source-derived company identities is currently failing tests for GLG-style aliases.

## Obsolete or Misleading
- `docs/architecture/module-plan.md` says several areas are scaffold-only, but those areas are now implemented.
- `docs/product/sprint-01-core-parity.md` is useful as a historical backlog, not as a reliable live-state document.
- `app/api/routes/bids.py`, `app/api/routes/settings.py`, and the `/upload` and `/uploads` redirect pages are thin compatibility surfaces rather than feature work.
- `app/modules/market_sources` and `app/modules/imports` are compatibility layers that should be treated as migration support, not new product surfaces.

## Product-Level Consequences
- The core discovery loop is usable, but location search is still string-based instead of radius-aware.
- Admins can prioritize source winners, but they cannot yet directly maintain all company/location mappings from the product UI.
- Users can create alerts and watchlists, but there is no clear delivery history or scheduled monitoring experience tied to them.
- The app can be operated locally and via scripts, but production-grade access control is not yet represented in the app itself.

