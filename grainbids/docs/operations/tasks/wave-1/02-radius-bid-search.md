# Task 2: Add Radius-Based Bid Search to Market Discovery

## Branch Slug
`codex/radius-bid-search`

## Objective
Add location-radius search to the bid discovery flow so users can find nearby grain bids using the existing location coordinates.

## Business Value
- Moves the product closer to a Farmbucks-style MVP.
- Makes the core discovery loop more useful for real farm decision-making.
- Uses existing location data to unlock a high-value search capability without a schema change.

## Background
The repository audit found that the active discovery experience already supports commodity, company, region, date, sort, and canonicality filters, but not physical proximity. The `locations` table already includes `latitude` and `longitude`, so the missing piece is query and UI wiring rather than new storage.

## Current Repository Context
- `apps/api/app/api/routes/normalized_prices.py` is the core discovery API.
- `apps/web/app/dashboard/page.tsx` is the main market UI.
- The dashboard is already a dense but functioning table-first experience.
- The likely implementation should stay local to discovery rather than spreading a new shared contract across unrelated modules.

## Exact Implementation Scope
- Add an origin-location plus radius filter to the normalized-prices discovery path.
- Use the existing `locations.latitude` and `locations.longitude` fields.
- Keep existing commodity, company, region, date, sort, and canonicality filters working.
- Add matching dashboard controls and query wiring.
- Add or update the backend tests that cover normalized-price filters and query helpers.

## Out-of-Scope Items
- No alert changes.
- No saved-search scheduling.
- No watchlist execution loop.
- No admin mapping editor.
- No auth/session changes.
- No Alembic migration.
- No global API client refactor unless absolutely necessary.

## Dependencies
- Task 1 should be merged or at least green first so the backend baseline is stable.

## Likely Files to Change
- `apps/api/app/api/routes/normalized_prices.py`
- `apps/web/app/dashboard/page.tsx`
- `apps/api/tests/test_normalized_price_filters.py`
- `apps/api/tests/test_normalized_price_query_helpers.py`
- `apps/web/lib/api.ts` only if a small query helper change is truly necessary

## Files That Must Not Change
- `apps/api/app/api/routes/alerts.py`
- `apps/web/app/alerts/page.tsx`
- `apps/web/app/sources/page.tsx`
- `apps/api/alembic/**`
- `apps/api/app/jobs/**`
- `apps/api/app/services/alert_*`

## Shared Contracts
- The normalized-prices query parameters are the shared API contract for the discovery flow.
- The dashboard filter bar is the shared UI contract for discovery search.
- `Location.latitude` and `Location.longitude` are the shared data backing the radius filter.

## Database Migration Requirements
- None. The existing `locations` table already has the required coordinates.

## API Contract Changes
- Add query parameters for origin location and radius, likely on the preview/summary/grouped/top-movers/facets discovery flow.
- Preserve the current behavior when the new parameters are absent.

## Frontend Contract Changes
- Add local dashboard filter state and UI controls for origin location and radius.
- Keep the current discovery controls intact.

## Acceptance Criteria
- The API can filter by origin plus radius.
- Rows without coordinates do not crash the query.
- Existing discovery filters still behave the same.
- The dashboard can submit the new filter and show filtered results.

## Tests
- Expand `test_normalized_price_filters.py` and `test_normalized_price_query_helpers.py` with radius coverage.
- Include missing-coordinate behavior and non-regression coverage for existing filters.
- Run the web build check if the environment allows it.

## Exact Test Commands
- `pytest -q tests/test_normalized_price_filters.py tests/test_normalized_price_query_helpers.py`
- `pytest -q`
- `npm run build`

## Risks
- Medium to high.
- Radius filtering can easily leak into shared helper code or disturb existing discovery behavior if the query path is changed too broadly.

## Reviewer Checklist
- Confirm the radius math is correct.
- Confirm null-coordinate behavior is explicit and deterministic.
- Confirm existing discovery filters still behave as before.
- Confirm the dashboard contract stayed local to the discovery page.

## Concurrency Restrictions
- Do not run concurrently with the admin mapping editor task because both would likely touch the dashboard/location-selection surface.
- This task can run alongside the notification-history task if the file boundaries stay isolated.
