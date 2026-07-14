from __future__ import annotations

from email.message import EmailMessage
import smtplib
import ssl

from app.core.config import settings


def send_smtp_message(message: EmailMessage) -> None:
    host = settings.alert_smtp_host
    if host is None:
        raise RuntimeError("ALERT_SMTP_HOST is required for outbound email")

    context = ssl.create_default_context()
    with smtplib.SMTP(host, settings.alert_smtp_port, timeout=20) as client:
        if settings.alert_smtp_use_tls:
            client.starttls(context=context)
        if settings.alert_smtp_username and settings.alert_smtp_password:
            client.login(settings.alert_smtp_username, settings.alert_smtp_password)
        client.send_message(message)
