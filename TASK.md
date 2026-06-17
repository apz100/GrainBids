# Task: Build out Settings page

## Objective
Replace the current Settings page shell with a real org settings, user management, and billing visibility page.

## Background
The settings page at `/settings` and the API at `/api/settings` are both stubs. The Organization and User models already exist with the needed fields. The request context and admin-gating infrastructure are already in place.

## Scope
- Add real API endpoints for org info and user management
- Build a functional settings UI with org info, user list, and billing visibility
- Admin-only gating for mutation endpoints

## Files likely to change
- `apps/api/app/api/routes/settings.py`
- `apps/web/app/settings/page.tsx`

## Constraints
- No Alembic migrations required
- Must use existing RequestContext and require_admin patterns
- Must not touch dashboard, alerts, watchlists, sources, or quotes
- Admin-only mutations (org update, user role update)

## Acceptance criteria
- Settings page shows org name, plan, and created_at
- Admin can update org name
- Settings page lists users with email, role, active status
- Admin can change a user's role
- Non-admin users see org info but no edit controls
- No existing functionality breaks

## Tests to run
- `cd apps/api; .\.venv\Scripts\python -m pytest -q`
- `cd apps/web; npx tsc --noEmit --pretty false`
