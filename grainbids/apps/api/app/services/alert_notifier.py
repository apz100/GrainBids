from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.notification_log import NotificationLog
from app.services.notification_delivery import send_email_message, send_webhook_message


def notify_new_alerts(db: Session, *, alert_ids: list[uuid.UUID]) -> None:
    if not alert_ids:
        return

    rows = db.execute(
        select(Alert, AlertRule)
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(Alert.id.in_(alert_ids))
        .order_by(Alert.triggered_at.desc())
    ).all()
    if not rows:
        return

    grouped: dict[uuid.UUID, list[tuple[Alert, AlertRule]]] = {}
    for alert, rule in rows:
        grouped.setdefault(rule.id, []).append((alert, rule))

    for rule_id, alerts_for_rule in grouped.items():
        rule = alerts_for_rule[0][1]
        channels = rule.notification_channels_json or _default_channels()

        for channel_cfg in channels:
            channel_type = channel_cfg.get("channel", "email")
            recipient = channel_cfg.get("recipient", "").strip()
            if not recipient:
                continue
            lines = _format_alert_lines(alerts_for_rule)
            subject = f"GrainBids: {len(alerts_for_rule)} alert(s) triggered"

            try:
                if channel_type == "webhook":
                    send_webhook_message(
                        url=recipient,
                        payload={
                            "subject": subject,
                            "alerts": [
                                {
                                    "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
                                    "rule_type": rule.rule_type,
                                    "comparison_operator": rule.comparison_operator,
                                    "threshold_value": float(rule.threshold_value),
                                    "message": alert.message,
                                }
                                for alert, _ in alerts_for_rule
                            ],
                        },
                    )
                else:
                    if not _email_config_available():
                        _log_notification(db, rule.org_id, alerts_for_rule, channel_type, recipient, "skipped",
                                          "email not configured at server level")
                        continue
                    send_email_message(
                        subject=subject,
                        to=recipient,
                        from_address=settings.alert_email_from,
                        body="\n".join(lines),
                    )

                for alert, _ in alerts_for_rule:
                    _log_notification(db, rule.org_id, [(alert, rule)], channel_type, recipient, "sent",
                                      payload={"subject": subject})
            except Exception as exc:
                for alert, _ in alerts_for_rule:
                    _log_notification(db, rule.org_id, [(alert, rule)], channel_type, recipient, "failed",
                                      error=str(exc), payload={"subject": subject})

    db.commit()


def _default_channels() -> list[dict]:
    if not settings.alert_email_enabled:
        return []
    to = (settings.alert_email_to or "").strip()
    if not to:
        return []
    return [{"channel": "email", "recipient": to}]


def _email_config_available() -> bool:
    return bool(settings.alert_smtp_host and settings.alert_email_from)


def _format_alert_lines(alerts_for_rule: list[tuple[Alert, AlertRule]]) -> list[str]:
    lines = ["GrainBids triggered alerts:", ""]
    for alert, rule in alerts_for_rule:
        lines.append(
            f"- [{alert.triggered_at.isoformat() if alert.triggered_at else 'unknown'}] "
            f"{rule.rule_type} {rule.comparison_operator} {float(rule.threshold_value):.4f} :: {alert.message}"
        )
    return lines


def _log_notification(
    db: Session,
    org_id: uuid.UUID,
    alerts_for_rule: list[tuple[Alert, AlertRule]],
    channel: str,
    recipient: str,
    status: str,
    *,
    error: str | None = None,
    payload: dict | None = None,
) -> None:
    for alert, _ in alerts_for_rule:
        db.add(
            NotificationLog(
                org_id=org_id,
                alert_id=alert.id,
                channel=channel,
                recipient=recipient,
                status=status,
                error_message=error,
                payload_json=payload,
            )
        )
