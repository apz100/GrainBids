# Product Gaps

## Implemented or Largely Implemented
- Farmbucks-style bid discovery exists in the dashboard and normalized-price API.
- Radius-based bid search now exists in the dashboard and normalized-price API.
- Company and elevator canonicalization exists in schema, resolver, backfill jobs, and source-priority controls.
- Commodity and delivery-period filters exist in the API and dashboard.
- Historical bid deltas exist through basis and cash/futures change columns plus carry-policy logic.
- Ingestion monitoring, run history, source freshness, and data-quality visibility are present.
- Saved searches and watchlists exist with CRUD and preview flows.
- Alerts exist with rule CRUD, recent-alert views, notification history, acknowledgement, resolution, and email notification hooks.
- Quote export exists.
- The DOCX benchmark filtering helper contract is restored and the DOCX seed path is back to passing collection and tests.
- Source-company backfill alias resolution for GLG-style cases is fixed and covered by tests.
- Notification delivery history is now visible in the Alerts UI and API.
- Production request-context hardening now exists: explicit org/user identity in production, deliberate local fallback only where configured, and admin-gated mutation routes.

## Partial
- The dashboard is responsive in CSS terms, but it is still a dense desktop-first table UI.
- The sources page exposes meaningful admin controls, but most mapping work is read-only or priority-based rather than a true editor for companies, locations, and source relationships.
- Signals exists as a product area, but it is not integrated into the core discovery workflow.
- `settings` is still a shell, so organization defaults, billing, and access controls are not productized in the UI.
- Root `/` is now a lightweight entry page; `/bids` is the active market dashboard, so the homepage is no longer a dashboard duplicate.

## Missing
- There is no dedicated company/location mapping editor in the web UI.
- Watchlists are CRUD + preview only; there is no scheduled watchlist execution/alert loop exposed to users.
- Price alerts exist, but the provider abstraction is still effectively email-only.
- Access control is still not a full external auth/session product, but it is no longer purely implicit header-based behavior in production.

## Obsolete or Misleading
- `docs/architecture/module-plan.md` says several areas are scaffold-only, but those areas are now implemented.
- `docs/product/sprint-01-core-parity.md` is useful as a historical backlog, not as a reliable live-state document.
- `app/api/routes/bids.py`, `app/api/routes/settings.py`, and the `/upload` and `/uploads` redirect pages are thin compatibility surfaces rather than feature work.
- `app/modules/market_sources` and `app/modules/imports` are compatibility layers that should be treated as migration support, not new product surfaces.

## Product-Level Consequences
- The core discovery loop is usable, and location search is now radius-aware instead of string-based.
- Admins can prioritize source winners, but they cannot yet directly maintain all company/location mappings from the product UI.
- Users can create alerts and watchlists, and alert delivery history is visible, but there is still no scheduled monitoring experience tied to watchlists.
- The app can be operated locally and via scripts, and production-grade access control is now represented through explicit request-context enforcement and mutation gating.
