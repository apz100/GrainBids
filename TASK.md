# Task: Add notification channel preferences to Alerts

## Objective
Allow per-alert-rule notification channel configuration (email, webhook) instead of using only global email settings.

## Background
The alert notifier currently sends all notifications to a single global email address. Users should be able to configure separate channels per rule.

## Scope
- Add `notification_channels_json` JSONB column to `alert_rules` table
- Create Alembic migration 0015
- Update notifier to dispatch per-rule channel configs
- Add API exposure for channel config on alert rules
- Add webhook delivery support (HTTP POST)
- Update alerts UI with channel configuration controls

## Files likely to change
- `apps/api/app/models/alert_rule.py`
- `apps/api/alembic/versions/0015_add_alert_notification_channels.py`
- `apps/api/app/services/alert_notifier.py`
- `apps/api/app/services/notification_delivery.py`
- `apps/api/app/api/routes/alerts.py`
- `apps/web/app/alerts/page.tsx`

## Constraints
- Must not change normalized prices, dashboard, sources, watchlists, or quotes
- Must not break existing email-only notifier behavior when no channels configured
- Must handle webhook failures gracefully (log, don't crash)

## Acceptance criteria
- Alert rules can have separate notification channel configs
- Email and webhook channels are supported
- When no channels are configured, falls back to global email settings
- Webhook delivery logs success/failure in notification_logs
- UI shows channel config per rule (for admin)
