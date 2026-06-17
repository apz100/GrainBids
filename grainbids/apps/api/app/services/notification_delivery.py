from __future__ import annotations

from email.message import EmailMessage
import smtplib
import ssl

from app.core.config import settings


def send_email_message(*, subject: str, to: str, from_address: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = to
    message.set_content(body)

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
