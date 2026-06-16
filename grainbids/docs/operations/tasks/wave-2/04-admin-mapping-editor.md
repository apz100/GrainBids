# Task 4. Build a real admin mapping editor

## Objective
Give admins a productized way to inspect and edit company/location mappings from the GrainBids UI, while keeping source priority controls and canonical coverage visible on the same admin surface.

## Business value
Admins currently have to lean on diagnostics, backfill jobs, or direct database changes to fix ambiguous company/location relationships. A real editor reduces manual intervention, shortens mapping turnaround, and makes the canonical data layer easier to trust.

## Background
- `apps/web/app/sources/page.tsx` already acts as the main admin source surface.
- `apps/api/app/api/routes/sources.py` already exposes source health, canonical coverage, and per-company source priority controls.
- `apps/api/app/api/routes/ingestion.py` already exposes ambiguous company/location diagnostics for admin review.
- The batch jobs `backfill_canonical_companies.py`, `backfill_canonical_locations.py`, and `consolidate_company_aliases.py` already encode the mapping rules, but they are operational tools rather than an interactive editor.
- `Location.company_id` is the current canonical mapping field, and the current product still lacks a first-class admin workflow for editing it directly.

## Exact scope
- Add an admin-gated API mutation for setting or clearing a location's `company_id` in the active org.
- Reuse the existing ambiguous-location diagnostics as the read model for the editor unless a small adapter endpoint is needed.
- Extend the `/sources` page with a company/location mapping editor section that shows current company assignments, candidate companies, and top source evidence for ambiguous locations.
- Keep the existing source priority controls and canonical coverage section visible and functional on the same page.
- Add the smallest useful tests to cover org scope, admin gating, and mapping update behavior.

## Out of scope
- Do not redesign the canonical matching algorithm.
- Do not change normalized-price discovery filters or the dashboard search flow.
- Do not modify alert evaluation, watchlists, quotes, or saved-search behavior.
- Do not add a new mapping engine or auto-merge workflow.
- Do not broaden the scope into a full organization settings product.
- Do not add unrelated refactoring or UI polish beyond what is needed for the editor to work.

## Dependencies
- Task 6 access-control hardening is already merged and should remain the basis for admin-only mutation behavior.
- Task 7 cleanup is already merged; use the current `/sources` route posture and current docs as the baseline.
- The mapping editor should preserve, not replace, the existing source priority controls.

## Likely files to change
- `apps/api/app/api/routes/sources.py`
- `apps/api/app/api/routes/ingestion.py` only if a tiny read-model adapter is needed
- `apps/api/tests/test_source_company_identity_diagnostics.py`
- `apps/api/tests/test_sources_location_company_mapping.py` or a similarly named new route test
- `apps/web/app/sources/page.tsx`
- `apps/web/lib/api.ts` only if the page needs a small contract helper

## Files that must not be changed
- `apps/api/app/api/routes/normalized_prices.py`
- `apps/web/app/dashboard/page.tsx`
- `apps/web/app/bids/page.tsx`
- `apps/api/app/jobs/backfill_canonical_companies.py`
- `apps/api/app/jobs/backfill_canonical_locations.py`
- `apps/api/app/jobs/consolidate_company_aliases.py`
- `apps/api/app/services/source_file_ingestion.py`
- `apps/api/app/services/upload_csv.py`
- `apps/web/app/alerts/page.tsx`
- `apps/web/app/watchlists/page.tsx`
- `apps/web/app/quotes/page.tsx`

## Shared contracts
- `RequestContext` and `require_admin`
- `Company`, `Location`, and `CompanySourcePriority` model semantics
- The existing ambiguous-location diagnostic payload
- The `/sources` admin page fetch pattern and API header helpers

## Migration requirements
- No Alembic migration is expected.
- If the implementation unexpectedly requires schema changes or audit-trail persistence, stop and reassess before adding a migration.

## API contract changes
- Add a small admin-only mutation endpoint for updating one location's company mapping.
- Keep the request and response shape minimal and explicit.
- Preserve the current ambiguous-location diagnostics response shape unless a tiny display-only field is required.
- Keep all endpoints org-scoped.

## Frontend contract changes
- Add a new mapping editor section to `/sources`.
- Show ambiguous locations with their current company, candidate companies, and source evidence.
- Allow admins to set or clear a location company mapping without leaving the page.
- Keep the existing source priority controls and canonical coverage view intact.

## Acceptance criteria
- An admin can inspect ambiguous company/location mappings from the UI.
- An admin can set or clear a location's company mapping from the UI.
- The page still shows source priority and canonical coverage controls.
- All changes are org-scoped and admin-gated.
- No unrelated discovery, alert, or quote behavior changes.

## Tests to add or update
- Route tests for the new mapping mutation endpoint.
- Route tests or service tests confirming org scope and admin gating.
- Existing ambiguous-location diagnostic tests if the read model needs a small adapter.
- Web build or type-check coverage for the updated `/sources` page.

## Exact test commands
- `cd apps/api; .\\.venv\\Scripts\\python -m pytest -q tests/test_source_company_identity_diagnostics.py tests/test_sources_location_company_mapping.py`
- `cd apps/api; .\\.venv\\Scripts\\python -m pytest -q`
- `cd apps/web; npx tsc --noEmit --pretty false`
- `cd apps/web; npm run build`

## Risks
- Mapping edits can accidentally mutate the wrong location if org scoping or admin checks are loose.
- The `/sources` page is already dense; the new editor must not break the existing source priority workflow.
- It is easy to widen the task into general canonicalization work; do not do that.
- No audit trail exists yet for mapping edits, so keep the mutation path small and explicit.

## Reviewer checklist
- Verify the mutation endpoint is admin-only and org-scoped.
- Verify a location company change only updates the intended location row.
- Verify the existing source priority and canonical coverage controls still work.
- Verify the `/sources` page remains usable and does not regress unrelated admin actions.
- Verify no migration or unrelated refactor slipped in.

## Concurrency restrictions
- Do not run this task in parallel with any other task that edits `apps/web/app/sources/page.tsx`.
- Do not run it in parallel with any task that changes location-selection or company-mapping semantics elsewhere in the app.
- Do not overlap with future dashboard filter work that could reuse the same company/location selection controls.

## Handoff notes
- Start by reading `CURRENT_STATE.md`, `PRODUCT_GAPS.md`, `ROADMAP.md`, and this task file.
- Inspect the existing source-admin implementation before adding new code.
- Keep the diff small and avoid unrelated cleanup.
- Commit the completed work, report the commit hash, and do not merge the branch.
