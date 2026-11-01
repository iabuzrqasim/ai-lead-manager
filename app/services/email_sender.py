"""Optional SMTP email sending, with safety rails.

- Sending is OFF unless EMAIL_SENDING_ENABLED=true.
- If EMAIL_TEST_INBOX is set, every email is redirected there instead of the real lead.
- Errors are caught and returned, never raised to the user as a crash.
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app.config import get_settings


@dataclass
class SendResult:
    ok: bool
    recipient: str | None
    error: str | None = None


def resolve_recipient(lead_email: str) -> str:
    settings = get_settings()
    return settings.email_test_inbox or lead_email


def send_email(to: str, subject: str, body: str) -> SendResult:
    settings = get_settings()
    if not settings.email_sending_enabled:
        return SendResult(ok=False, recipient=None, error="Email sending is disabled (EMAIL_SENDING_ENABLED=false).")
    if not (settings.smtp_host and settings.smtp_from):
        return SendResult(ok=False, recipient=None, error="SMTP is not configured (SMTP_HOST / SMTP_FROM).")

    recipient = resolve_recipient(to)
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        return SendResult(ok=False, recipient=recipient, error=f"{type(exc).__name__}: {exc}")
    return SendResult(ok=True, recipient=recipient)
