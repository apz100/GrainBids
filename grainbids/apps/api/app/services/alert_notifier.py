from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.notification_log import NotificationLog
from app.services.notification_delivery import send_email_message


def notify_new_alerts(db: Session, *, alert_ids: list[uuid.UUID]) -> None:
    if not settings.alert_email_enabled or not alert_ids:
        return

    if not settings.alert_email_to or not settings.alert_email_from:
        _log_skipped_notifications(db, alert_ids=alert_ids, reason="missing email recipient configuration")
        return

    if not settings.alert_smtp_host:
        _log_skipped_notifications(db, alert_ids=alert_ids, reason="missing smtp host")
        return

    rows = db.execute(
        select(Alert, AlertRule)
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(Alert.id.in_(alert_ids))
        .order_by(Alert.triggered_at.desc())
    ).all()
    if not rows:
        return

    lines = ["GrainBids triggered alerts:", ""]
    for alert, rule in rows:
        lines.append(
            f"- [{alert.triggered_at.isoformat() if alert.triggered_at else 'unknown'}] "
            f"{rule.rule_type} {rule.comparison_operator} {float(rule.threshold_value):.4f} :: {alert.message}"
        )

    try:
        subject = f"GrainBids: {len(rows)} alert(s) triggered"
        send_email_message(
            subject=subject,
            to=settings.alert_email_to,
            from_address=settings.alert_email_from,
            body="\n".join(lines),
        )
        for alert, rule in rows:
            db.add(
                NotificationLog(
                    org_id=rule.org_id,
                    alert_id=alert.id,
                    channel="email",
                    recipient=settings.alert_email_to,
                    status="sent",
                    payload_json={"subject": subject},
                )
            )
        db.commit()
    except Exception as exc:
        for alert, rule in rows:
            db.add(
                NotificationLog(
                    org_id=rule.org_id,
                    alert_id=alert.id,
                    channel="email",
                    recipient=settings.alert_email_to,
                    status="failed",
                    error_message=str(exc),
                    payload_json={"subject": subject},
                )
            )
        db.commit()
        raise


def _log_skipped_notifications(db: Session, *, alert_ids: list[uuid.UUID], reason: str) -> None:
    if not alert_ids:
        return
    rows = db.execute(
        select(Alert, AlertRule)
        .join(AlertRule, AlertRule.id == Alert.alert_rule_id)
        .where(Alert.id.in_(alert_ids))
    ).all()
    for alert, rule in rows:
        db.add(
            NotificationLog(
                org_id=rule.org_id,
                alert_id=alert.id,
                channel="email",
                recipient=settings.alert_email_to,
                status="skipped",
                error_message=reason,
            )
        )
    db.commit()
