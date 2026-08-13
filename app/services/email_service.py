from __future__ import annotations

import logging
from pathlib import Path
from string import Template

from pydantic import NameEmail, SecretStr

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / 'templates' / 'emails'


def render_template(name: str, **context) -> str:
    """Render an HTML email template with provided context."""
    if not name.endswith('.html'):
        name = f'{name}.html'
    template_path = _TEMPLATES_DIR / name
    if not template_path.is_file():
        logger.warning('Email template %s not found at %s', name, template_path)
        # Fallback basic html rendering if template file is missing
        items = ''.join(f'<li><strong>{k}:</strong> {v}</li>' for k, v in context.items())
        return f'<div><p>Notification Payload:</p><ul>{items}</ul></div>'
    template = Template(template_path.read_text(encoding='utf-8'))
    return template.safe_substitute(**context)


def _render_template(name: str, **context) -> str:
    return render_template(name, **context)



async def _send_via_smtp(to_email: str, subject: str, html: str) -> None:
    """Send an e-mail through the configured SMTP server.

    If ``SMTP_HOST`` is not set the application falls back to logging the
    message (development mode), so the code never crashes without SMTP.
    """
    settings = get_settings()

    if not settings.SMTP_HOST:
        logger.info(
            'SMTP not configured — would send e-mail to %s\nSubject: %s\nBody: %s',
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
        MAIL_PASSWORD=SecretStr(settings.SMTP_PASSWORD),
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
        recipients=[NameEmail(name=to_email, email=to_email)],
        body=html,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message)


async def send_password_reset_email(to_email: str, reset_link: str) -> None:
    subject = 'Password reset'
    html = _render_template(
        'password_reset.html',
        reset_link=reset_link,
    )
    await _send_via_smtp(to_email, subject, html)


async def send_verification_email(to_email: str, verify_link: str) -> None:
    subject = 'Verify your email'
    html = _render_template(
        'account_created.html',
        verify_link=verify_link,
    )
    await _send_via_smtp(to_email, subject, html)
