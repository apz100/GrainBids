# Task 8. Add a read-only billing and entitlement shell

## Objective
Add a minimal, customer-facing billing and entitlement surface that exposes the current org plan and upgrade path without changing auth/session behavior, discovery, alerts, watchlists, or ingestion.

## Business value
This gives GrainBids a concrete paid-plan entry point and a place to surface plan status before any monetization enforcement work. It is a low-risk step toward a revenue-ready product because it helps users understand their current tier and where an upgrade would land, without disturbing the working market, alert, and ingestion flows.

## Background
- `app/_components/top-nav.tsx` already shows the main routes and can carry a lightweight billing entry point.
- `app/core/request_context.py` and Task 6 already established explicit org/user access control semantics for production.
- `organizations.plan` already exists in the data model.
- The rejected billing work bundled this task with a broader auth/session rewrite; that broader change should stay out of this task.

## Exact scope
- Add a small read-only billing API surface that returns the current org plan and a stable list of included/upgrade capabilities.
- Add a `/billing` page that shows the current plan, what it includes, and the obvious upgrade path.
- Add a small navigation entry point from the top nav if useful.
- Keep the surface informational only. Do not enforce limits, hide product features, or change any existing product behavior.
- Keep the implementation narrowly scoped to plan display and upgrade presentation.

## Out of scope
- Do not implement sign-in, sign-out, login, callback, or session issuance flows.
- Do not change `RequestContext`, auth bootstrap, or request-context mode selection.
- Do not change discovery, watchlists, alerts, quotes, signals, radius search, or ingestion behavior.
- Do not add billing provider integrations, checkout flows, invoices, or payments.
- Do not add entitlement enforcement gates to existing product features.
- Do not broaden into organization settings, invitations, password reset, or multi-org switching.
- Do not modify the Settings page session flow or any other unrelated account-management screen.

## Dependencies
- Task 6 access-control hardening is the prerequisite baseline.
- This task should assume the existing org/user context model and should not introduce a new identity system.
- If the current worktree still contains unmerged auth/session bootstrap work, keep that separate from this task.

## Likely files to change
- `apps/api/app/api/routes/settings.py`
- `apps/api/app/services/entitlements.py`
- `apps/api/tests/test_entitlements.py`
- `apps/api/tests/test_settings_billing.py`
- `apps/web/app/billing/page.tsx`
- `apps/web/app/_components/top-nav.tsx`
- `apps/web/lib/api.ts` only if a tiny helper is needed for the read-only fetch

## Files that must not be changed
- `apps/api/app/core/request_context.py`
- `apps/api/app/api/routes/auth.py`
- `apps/api/app/core/session_auth.py`
- `apps/web/middleware.ts`
- `apps/web/app/login/**`
- `apps/web/app/auth/**`
- `apps/web/app/dashboard/page.tsx`
- `apps/web/app/watchlists/page.tsx`
- `apps/web/app/alerts/page.tsx`
- `apps/web/app/quotes/page.tsx`
- `apps/web/app/sources/page.tsx`
- `apps/web/app/signals/page.tsx`
- ingestion jobs and discovery route files

## Shared contracts
- `RequestContext`
- `require_admin`
- `Organization.plan`
- current org-scoped request helper behavior
- the existing top-nav navigation pattern

## Migration requirements
- No Alembic migration is expected.

## API contract changes
- Add or refine a small read-only settings/billing endpoint that returns:
  - current plan
  - readable plan label
  - included capabilities
  - upgrade or contact path
- Keep the response shape minimal and stable.
- Do not change mutation contracts.

## Frontend contract changes
- Add a billing entry point from the top nav.
- Render the current plan and plan benefits in a simple read-only layout.
- Keep the existing Settings page unchanged.
- Do not hide or disable unrelated product areas.

## Acceptance criteria
- A signed-in user can view the org plan and upgrade information from the product UI.
- The billing view is read-only.
- No auth/session behavior changes are introduced by this task.
- No discovery, alert, watchlist, or ingestion behavior changes are introduced by this task.

## Tests to add or update
- Route tests for the billing/settings endpoint.
- Service tests for entitlement normalization or plan label mapping.
- A focused web typecheck or build check for the updated Billing UI.

## Exact test commands
- `cd apps/api; .\\.venv\\Scripts\\python -m pytest -q tests/test_entitlements.py tests/test_settings_billing.py`
- `cd apps/api; .\\.venv\\Scripts\\python -m pytest -q`
- `cd apps/web; npx tsc --noEmit --pretty false`
- `cd apps/web; npm run build`

## Risks
- It is easy to accidentally drag auth/session rewiring back into the task; do not do that.
- The Settings page is already doing real admin work, so billing additions should not modify it.
- If the endpoint shape grows beyond a simple plan summary, it will start to look like a broader account-settings project.

## Reviewer checklist
- Verify the billing surface is read-only.
- Verify the task did not alter auth/session plumbing.
- Verify no discovery, watchlist, alert, quote, signals, or ingestion code changed.
- Verify the plan data is displayed clearly and consistently.
- Verify the change set remains small and reviewable.

## Concurrency restrictions
- Do not run this task in parallel with any task that edits `apps/api/app/core/request_context.py` or `apps/api/app/api/routes/auth.py`.
- Do not run it in parallel with any task that edits `apps/web/app/settings/page.tsx`; this task should not touch Settings.
- Do not run it in parallel with feature work that depends on new billing enforcement, because enforcement is out of scope here.

## Handoff notes
- Start by reading `CURRENT_STATE.md`, `PRODUCT_GAPS.md`, `ROADMAP.md`, and this task file.
- Inspect the top-nav implementation before editing.
- Keep the task additive and do not widen it into a full auth or billing provider project.
- Commit the work, report the commit hash, and do not merge the branch.
