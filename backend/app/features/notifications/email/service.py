"""Email delivery: writes an `outbox_emails` row and sends over SMTP.

`send_email` is the entry point every feature calls (CQ-014's OTP code,
later CQ-015/CQ-020/CQ-024/CQ-034): it inserts a `QUEUED` `OutboxEmail` row
first so the demo outbox always reflects the attempt, then sends through
`smtp_send` and marks the row `SENT` or `FAILED`. `smtp_send` is a
module-level function (not inlined) so tests can monkeypatch
`service.smtp_send` without a live SMTP server; delivery failure is logged
and swallowed, never raised, so a down SMTP server doesn't break callers
that must still return (e.g. the OTP-issue endpoint).
"""

import logging
import re
import uuid
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_tags(html: str) -> str:
    """Crude HTML -> text fallback for the plain-text MIME alternative."""
    return _WHITESPACE_RE.sub(" ", _TAG_RE.sub("", html)).strip()


async def smtp_send(*, to: str, subject: str, html: str) -> None:
    """Builds a text+html message and sends it via SMTP (Mailpit locally).

    No TLS/auth: local and demo delivery target Mailpit, which accepts
    plain SMTP on `settings.smtp_port`.
    """
    settings = get_settings()

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(_strip_tags(html))
    message.add_alternative(html, subtype="html")

    await aiosmtplib.send(message, hostname=settings.smtp_host, port=settings.smtp_port)


async def send_email(
    db: AsyncSession,
    *,
    to: str,
    subject: str,
    html: str,
    application_id: uuid.UUID | None = None,
) -> OutboxEmail:
    """Records and sends one email; returns the `OutboxEmail` row.

    Does not commit — the caller owns the transaction, so the outbox row
    lands (or rolls back) together with whatever else the caller writes.
    """
    outbox_email = OutboxEmail(
        to_email=to,
        subject=subject,
        html=html,
        application_id=application_id,
        status=EmailStatus.QUEUED,
    )
    db.add(outbox_email)
    await db.flush()

    try:
        await smtp_send(to=to, subject=subject, html=html)
    except Exception:
        logger.exception("Failed to send email to %s", to)
        outbox_email.status = EmailStatus.FAILED
    else:
        outbox_email.status = EmailStatus.SENT

    await db.flush()
    return outbox_email
