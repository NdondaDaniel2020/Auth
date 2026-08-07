from __future__ import annotations

import logging
from pathlib import Path
from string import Template

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / 'templates' / 'emails'


def _render_template(name: str, **context) -> str:
    template_path = _TEMPLATES_DIR / name
    template = Template(template_path.read_text(encoding='utf-8'))
    return template.substitute(**context)


def _send_via_smtp(to_email: str, subject: str, html: str) -> None:
    """Send an e-mail through the configured SMTP server.

    If ``SMTP_HOST`` is not set the application falls back to logging the
    message (development mode), so the code never crashes without SMTP.
    """
    settings = get_settings()

    if not settings.SMTP_HOST:
        logger.info(
            "SMTP not configured — would send e-mail to %s\nSubject: %s\nBody: %s",
            to_email,
            subject,
            html,
        )
        return

    from fastapi_mail import (
        ConnectionConfig,
        FastMail,
        MessageSchema,
        MessageType,
    )

    conf = ConnectionConfig(
        MAIL_USERNAME=settings.SMTP_USER,
        MAIL_PASSWORD=settings.SMTP_PASSWORD,
        MAIL_FROM=settings.SMTP_FROM or settings.SMTP_USER,
        MAIL_PORT=settings.SMTP_PORT,
        MAIL_SERVER=settings.SMTP_HOST,
        MAIL_STARTTLS=settings.SMTP_TLS,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=bool(settings.SMTP_USER),
        VALIDATE_CERTS=True,
    )

    message = MessageSchema(
        subject=subject,
        recipients=[to_email],
        body=html,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    fm.send_message(message)


async def send_password_reset_email(to_email: str, reset_link: str) -> None:
    subject = 'Password reset'
    html = _render_template(
        'password_reset.html',
        reset_link=reset_link,
    )
    _send_via_smtp(to_email, subject, html)


async def send_verification_email(to_email: str, verify_link: str) -> None:
    subject = 'Verify your email'
    html = _render_template(
        'account_created.html',
        verify_link=verify_link,
    )
    _send_via_smtp(to_email, subject, html)
