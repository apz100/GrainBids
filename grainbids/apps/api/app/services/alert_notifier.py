from __future__ import annotations

from email.message import EmailMessage
import smtplib
import ssl
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.alert_rule import AlertRule


def notify_new_alerts(db: Session, *, alert_ids: list[uuid.UUID]) -> None:
    if not settings.alert_email_enabled or not alert_ids:
        return

    if not settings.alert_email_to or not settings.alert_email_from:
        return

    if not settings.alert_smtp_host:
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

    message = EmailMessage()
    message["Subject"] = f"GrainBids: {len(rows)} alert(s) triggered"
    message["From"] = settings.alert_email_from
    message["To"] = settings.alert_email_to
    message.set_content("\n".join(lines))

    _send(message)


def _send(message: EmailMessage) -> None:
    host = settings.alert_smtp_host
    port = settings.alert_smtp_port
    username = settings.alert_smtp_username
    password = settings.alert_smtp_password
    use_tls = settings.alert_smtp_use_tls

    if host is None:
        return

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as client:
        if use_tls:
            client.starttls(context=context)
        if username and password:
            client.login(username, password)
        client.send_message(message)
