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
- Watchlists now have scheduled automation support: enable/disable, daily digest runs, linked saved-search-backed alert promotion, and digest history visibility.
- Quote export exists.
- The DOCX benchmark filtering helper contract is restored and the DOCX seed path is back to passing collection and tests.
- Source-company backfill alias resolution for GLG-style cases is fixed and covered by tests.
- Notification delivery history is now visible in the Alerts UI and API.
- Production request-context hardening now exists: explicit org/user identity in production, deliberate local fallback only where configured, and admin-gated mutation routes.
- A production-safe session bootstrap path now exists: the API exposes session details, the web app uses a same-origin session bridge, and admin navigation/session-aware pages no longer depend on browser-exposed production identity headers.

## Partial
- The dashboard is responsive in CSS terms, but it is still a dense desktop-first table UI.
- The sources page exposes meaningful admin controls, including company/location mapping editor controls, but the workflow is still narrower than a full bulk-management workspace.
- Signals exists as a product area, but it is not integrated into the core discovery workflow.
- `settings` now covers session-aware org and user-role basics, but billing, invites, and broader account administration are still not productized in the UI.
- Root `/` is now a lightweight entry page; `/bids` is the active market dashboard, so the homepage is no longer a dashboard duplicate.

## Missing
- Price alerts exist, but the provider abstraction is still effectively email-only.
- A full external auth product is still missing: there is no complete sign-in/sign-out/callback UX or provider-managed session issuance flow in the product itself yet.

## Obsolete or Misleading
- `docs/architecture/module-plan.md` has been synchronized with the current implementation and should be treated as the active architecture reference.
- `docs/product/sprint-01-core-parity.md` remains a historical backlog record, not a reliable live-state document.
- `app/api/routes/bids.py`, `app/api/routes/settings.py`, and the `/upload` and `/uploads` redirect pages are thin compatibility surfaces rather than feature work.
- `app/modules/market_sources` and `app/modules/imports` are compatibility layers that should be treated as migration support, not new product surfaces.

## Product-Level Consequences
- The core discovery loop is usable, and location search is now radius-aware instead of string-based.
- Admins can prioritize source winners and directly maintain company/location mappings from the product UI.
- Users can create alerts and watchlists, and both alert and watchlist delivery history are visible; watchlists can now run scheduled automation loops that promote matching filters into alert rules.
- The app can be operated locally and via scripts, and production-grade access control now includes explicit request-context enforcement plus a same-origin session bootstrap path for the web shell.
