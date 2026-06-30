# Task 9. Bootstrap production auth and sessions

## Objective
Add a minimal production-grade authenticated session path so GrainBids can identify the active user and org without relying on `NEXT_PUBLIC_AUTH_USER_ID` as the production identity source, while preserving the current local-dev header flow where it is intentionally supported.

## Business value
This is the smallest credible step toward a tenant-aware SaaS onboarding flow. It makes the app safer to operate for paying customers by giving production a real identity/session model, while preserving the existing discovery, alerts, watchlists, and ingestion behavior that already works.

## Background
- `app/core/request_context.py` already enforces explicit production identity semantics from Task 6.
- The current product still treats access control as a missing full auth/session product in `PRODUCT_GAPS.md`.
- The billing shell from Task 8 is separate and should remain read-only; this task is about identity and route protection, not monetization enforcement.
- Local development header auth is still intentionally supported in the repo and must remain available where explicitly enabled.

## Exact scope
- Add a minimal sign-in/session bootstrap flow for production.
- Add a current-user/bootstrap API surface so the web app can resolve the active user, org, and role after login.
- Make the web shell redirect unauthenticated users to login instead of loading product pages directly in production.
- Keep the existing local-dev header flow intact where the repo already supports it.
- Reuse the existing `users` table and `org_id` model for MVP.
- Keep the change narrow enough that discovery, alerts, watchlists, quotes, signals, and ingestion continue to behave the same.

## Out of scope
- Do not add billing, entitlements, checkout, invoices, or enforcement gates.
- Do not add a multi-org switching UI.
- Do not add invitations, password reset polish, billing-provider integrations, or admin provisioning flows.
- Do not refactor the scraper or ingestion pipeline.
- Do not change discovery, alerts, watchlists, quotes, signals, or source-management semantics.
- Do not broaden the task into a full account-settings rewrite.
- Do not remove the deliberate local-dev header support that already exists.

## Dependencies
- Task 6 request-context hardening is the prerequisite baseline.
- This task should use the current `users`/`org_id` identity model rather than introducing a separate membership system unless a concrete blocker appears.
- If auth/session bootstrap touches any shared UI contract, keep it minimal and stable.

## Likely files to change
- `apps/api/app/api/routes/auth.py`
- `apps/api/app/core/session_auth.py`
- `apps/api/app/core/request_context.py` only if a narrow production identity hook is required
- `apps/api/tests/test_auth_routes.py`
- `apps/api/tests/test_request_context.py`
- `apps/api/tests/test_route_authorization.py`
- `apps/web/middleware.ts`
- `apps/web/lib/api.ts`
- `apps/web/app/login/**`
- `apps/web/app/auth/**`
- `apps/web/app/_components/auth-session-provider.tsx`

## Files that must not be changed
- `apps/api/app/api/routes/normalized_prices.py`
- `apps/api/app/api/routes/alerts.py`
- `apps/api/app/api/routes/watchlists.py`
- `apps/api/app/api/routes/sources.py`
- `apps/api/app/services/source_file_ingestion.py`
- `apps/api/app/services/alert_evaluator.py`
- `apps/api/app/services/alert_notifier.py`
- `apps/web/app/dashboard/page.tsx`
- `apps/web/app/alerts/page.tsx`
- `apps/web/app/watchlists/page.tsx`
- `apps/web/app/sources/page.tsx`
- `apps/web/app/quotes/page.tsx`
- `apps/web/app/signals/page.tsx`
- `apps/web/app/settings/page.tsx`
- ingestion jobs and discovery route files

## Shared contracts
- `RequestContext`
- `require_admin`
- `users.org_id`
- the production identity resolution path
- the web app's session/bootstrap response contract
- the login and protected-route redirect contract

## Migration requirements
- No Alembic migration is expected for the MVP path.

## API contract changes
- Add a minimal current-user or session-bootstrap response that returns:
  - active user id
  - org id
  - role
  - display name or email if already available
  - a simple authenticated/unauthenticated indicator
- Add or refine the login/callback/session endpoints needed for production bootstrap.
- Keep the response shape minimal and stable.
- Do not change unrelated mutation contracts.

## Frontend contract changes
- Add a login entry point and a protected-route behavior in the web shell.
- Ensure authenticated pages can resolve the active user and org after login.
- Preserve the local-dev header-based flow where it is already intentionally used.
- Keep the rest of the product pages visually and behaviorally unchanged.

## Acceptance criteria
- Production pages require authenticated identity rather than an ad hoc user-id header.
- Unauthenticated users are redirected to login in the web shell.
- Local development header auth still works where explicitly enabled.
- Admin-only routes still reject non-admin users.
- Existing discovery, alerts, watchlists, quotes, and ingestion flows continue to behave the same.

## Tests to add or update
- API config and request-context tests for production identity enforcement.
- Auth route tests for current-user/bootstrap and unauthenticated rejection.
- Route authorization tests for admin-only and authenticated-only paths.
- Web type-check and build checks for the auth shell changes.

## Exact test commands
- `cd apps/api; .\\.venv\\Scripts\\python -m pytest -q tests/test_auth_routes.py tests/test_request_context.py tests/test_route_authorization.py`
- `cd apps/api; .\\.venv\\Scripts\\python -m pytest -q`
- `cd apps/web; npx tsc --noEmit --pretty false`
- `cd apps/web; npm run build`

## Risks
- Auth/session work can easily disturb the existing local-dev header flow if it is widened too much.
- Web redirect logic can introduce loops if the bootstrap response contract is inconsistent.
- It is easy to accidentally pull this into billing, settings, or entitlement work; keep those separate.
- Existing pages may assume headers are always present, so the adapter layer needs to stay narrow.

## Reviewer checklist
- Verify production identity no longer depends on `NEXT_PUBLIC_AUTH_USER_ID`.
- Verify local-dev header support still works where explicitly enabled.
- Verify unauthenticated users are redirected before loading protected product pages.
- Verify admin-only routes still reject non-admin users.
- Verify discovery, alerts, watchlists, quotes, signals, and ingestion were not changed.
- Verify the API and web contracts are minimal and stable.

## Concurrency restrictions
- Do not run this task in parallel with Task 8 or any other task that edits auth/session plumbing.
- Do not run it in parallel with any task that edits `apps/web/app/settings/page.tsx`.
- Do not run it in parallel with any task that depends on new billing enforcement or membership-model changes.

## Handoff notes
- Start by reading `CURRENT_STATE.md`, `PRODUCT_GAPS.md`, `ROADMAP.md`, and this task file.
- Inspect the current auth/session and request-context implementation before editing.
- Keep the diff minimal and preserve all working discovery and ingestion behavior.
- Commit the work, report the commit hash, and do not merge your own branch.
