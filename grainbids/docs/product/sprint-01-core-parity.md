# Sprint 01 - Core Parity Foundation

Scope: stabilize GrainBids runtime, then implement Farmbucks-style core flow (ingestion -> market search -> watchlist -> alerts).

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
- Canonicalize source/company/location names during normalization.
- Add deterministic dedupe keys for repeated "Any <Branch>" style rows.
- Keep scheduled runs at 08:00 and 15:00 America/Toronto.
- Add ingestion run triage view (top reject reasons by source).

### 2) Market search parity (P0)
- Add canonical entities:
  - `companies`
  - `locations` (with postal/lat/lng fields)
  - mapping table between company + location
- Build market search endpoint for:
  - commodity
  - location origin
  - radius
  - delivery month
- Return grouped rows by delivery month and sorted by price.

### 3) Watchlists + alerts parity (P0)
- Add `saved_searches` with month scoping and target values.
- Extend alert rules to support saved-search linkage + month windows.
- Add notification log table and provider abstraction (email now, SMS next).

### 4) Dashboard UX parity (P1)
- Keep `/bids` table-first layout:
  - first fold: quick filters + live table
  - second fold: top basis movers
  - third fold: open alerts actions
- Add grouped month sections and "top N bids per month" panel.
- Keep `/sources` admin-only.

## Definition of Done (Sprint 01)

1. One-click smoke test passes for API + org-scoped market endpoints.
2. `/bids` loads live rows by default with no manual query entry.
3. Location and company filters are canonicalized and de-duplicated.
4. At least one scheduled ingestion cycle/day updates market data successfully.
5. Saved search + alert trigger loop works end-to-end for one pilot org.
