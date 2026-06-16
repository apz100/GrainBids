# Sprint 01 - Core Parity Foundation

Scope: stabilize GrainBids runtime, then implement Farmbucks-style core flow (ingestion -> market search -> watchlist -> alerts).

Status note: this is now a historical sprint backlog. Use `CURRENT_STATE.md`, `PRODUCT_GAPS.md`, and `docs/architecture/module-plan.md` for the live product surface.

## Phase 0 (Hardening, must finish first)

1. Single active runtime path
   - Keep `apps/web` + `apps/api` as the only runtime stack.
   - Treat `apps/api/legacy_runtime` and `apps/api/legacy_source_ingest` as reference-only.
2. Environment guardrails
   - Enforce production API runtime validation (`DATABASE_URL`, `ALLOW_IMPLICIT_ORG=false`, CORS list).
   - Enforce web API context checks (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_ORG_ID`).
3. Contract smoke tests
   - Validate:
     - `GET /health/live`
     - `GET /health/ready`
     - `GET /api/health/db`
     - org-scoped endpoints with headers:
       - `GET /api/ingestion/sla`
       - `GET /api/normalized-prices/summary`
       - `GET /api/normalized-prices/facets`
       - `GET /api/normalized-prices/preview?limit=10`
4. Data quality baselines
   - Track parse success, rejects, duplicates, missing required fields per run.
   - Keep source health/freshness visible.

## Sprint Backlog (Execution order)

### 1) Ingestion reliability (P0)
- Done: source/company/location canonicalization exists in the ingestion flow.
- Done: repeated source rows are handled through deterministic normalized-price persistence and diagnostics.
- Done: scheduled ingestion scripts target 08:00 and 15:00 America/Toronto.
- Done: ingestion SLA, run history, diagnostics, and reject-quality visibility are available from the API and Sources UI.

### 2) Market search parity (P0)
- Done: canonical `companies` and `locations` tables exist, including postal code and latitude/longitude on locations.
- Done: market search supports commodity, company, region/location text, delivery month, and origin/radius search.
- Done: grouped monthly preview, top movers, and sorted preview rows are exposed through normalized-price APIs and the dashboard.

### 3) Watchlists + alerts parity (P0)
- Done: saved searches and watchlists exist with CRUD and preview flows.
- Done: alert rules exist with CRUD, recent-alert visibility, acknowledgement, and resolution.
- Done: notification logs are durable and visible; the active provider path is email.
- Still open: scheduled watchlist execution and non-email notification providers are not productized.

### 4) Dashboard UX parity (P1)
- Done: `/bids` is the table-first market layout with quick filters, live table, grouped preview, top movers, alert creation, watchlist creation, and open-alert actions.
- Done: `/sources` is admin-only in the navigation and exposes source health, canonical coverage, source priority, company/location mapping editor controls, ingestion runs, and manual ingestion triggers.
- Current route posture: `/` is a lightweight entry page, not a duplicate dashboard; deprecated `/upload` and `/uploads` routes redirect to `/sources`.

## Definition of Done (Sprint 01)

1. One-click smoke test passes for API + org-scoped market endpoints.
2. `/bids` loads live rows by default with no manual query entry.
3. Location and company filters are canonicalized and de-duplicated.
4. At least one scheduled ingestion cycle/day updates market data successfully.
5. Saved search + alert trigger loop works end-to-end for one pilot org.

## Remaining Follow-Up
- Productize scheduled watchlist execution.
- Expand notification providers beyond email.
- Complete the Settings surface for organization defaults, billing, and access controls.
