# Task 3: Add Alert Notification History Visibility

## Branch Slug
`codex/alert-notification-history`

## Objective
Expose alert notification delivery history in the product UI so users can see sent, skipped, and failed notification attempts.

## Business Value
- Makes alert delivery outcomes visible and actionable.
- Closes an observability gap in the alerting workflow.
- Improves trust in alerting without changing alert-evaluation behavior.

## Background
The backend already writes `notification_logs` through `apps/api/app/services/alert_notifier.py`, but the Alerts page only exposes alert rules and recent alerts. The product lacks a user-facing history of delivery attempts, recipient/channel details, provider message IDs, and failure reasons.

## Current Repository Context
- `notification_logs` already exists in the schema and is written by the notifier.
- The alerts UI is real and already supports rule CRUD and recent alert views.
- This task should be read-only from the alert-evaluation perspective.
- A clean, local UI addition is preferable to broad API plumbing changes.

## Exact Implementation Scope
- Add a read-only notification-log endpoint under the alerts surface or a dedicated notification route if needed.
- Surface notification history in the Alerts page.
- Include delivery status, channel, recipient, provider message ID, error message, and timestamp.
- Keep notifier write behavior unchanged unless a tiny serializer or projection helper is required.
- Add the smallest useful backend and UI tests.

## Out-of-Scope Items
- No alert-evaluation logic changes.
- No watchlist scheduling changes.
- No radius-search work.
- No admin mapping editor.
- No auth/session changes.
- No Alembic migration.
- No changes to unrelated discovery code.

## Dependencies
- Task 1 should be merged or at least green first so the backend baseline is clean.

## Likely Files to Change
- `apps/api/app/api/routes/alerts.py`
- `apps/web/app/alerts/page.tsx`
- `apps/api/tests/test_alert_notification_logs.py` if a new route test file is added
- `apps/api/tests/test_alert_evaluator.py` only if notifier coverage needs a small extension

## Files That Must Not Change
- `apps/api/app/api/routes/normalized_prices.py`
- `apps/web/app/dashboard/page.tsx`
- `apps/web/app/sources/page.tsx`
- `apps/api/alembic/**`
- `apps/api/app/jobs/**`

## Shared Contracts
- `NotificationLog` row shape.
- Alerts route response shapes.
- The Alerts page row type for recent alert and notification history rendering.

## Database Migration Requirements
- None. `notification_logs` already exists.

## API Contract Changes
- Add a read-only notification-history endpoint, likely `GET /api/alerts/notification-logs`.
- Keep the response org-scoped and safe for read-only consumption.

## Frontend Contract Changes
- Add a local notification-log row type.
- Add a notification-history section or table in the Alerts page.

## Acceptance Criteria
- A user can view notification attempts and statuses in the product UI.
- The endpoint is org-scoped.
- Sent, skipped, and failed statuses are visible.
- No delivery write path regressed.

## Tests
- Add route coverage for the notification-history endpoint.
- Add or extend notifier/logging coverage if serializer logic changes.
- Add a web build check.

## Exact Test Commands
- `pytest -q tests/test_alert_evaluator.py tests/test_alert_notification_logs.py`
- `pytest -q`
- `npm run build`

## Risks
- Medium.
- The main risk is expanding scope into alert-evaluation or admin mutation behavior when the task only needs read-only visibility.

## Reviewer Checklist
- Confirm the history endpoint is read-only and org-scoped.
- Confirm the UI clearly shows sent, skipped, and failed delivery attempts.
- Confirm the notifier write path stayed unchanged.
- Confirm the new code stayed isolated to alerts-related files.

## Concurrency Restrictions
- Do not run concurrently with any task that changes request-context or admin-gating behavior.
- This task can run alongside the radius-search task if file boundaries stay isolated.
