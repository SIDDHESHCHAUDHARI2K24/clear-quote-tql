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
from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class EmailAttachment:
    """CQ-020: a file attached to an email (the pre-approval letter PDF)."""

    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "pdf"


def build_message(
    *,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    attachments: Sequence[EmailAttachment] = (),
) -> EmailMessage:
    """text + html alternatives (`text` defaults to the tag-stripped html),
    plus any attachments (CQ-020)."""
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text if text is not None else _strip_tags(html))
    message.add_alternative(html, subtype="html")
    for attachment in attachments:
        message.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )
    return message


async def smtp_send(
    *,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    attachments: Sequence[EmailAttachment] = (),
) -> None:
    """Builds a text+html message and sends it via SMTP (Mailpit locally).

    No TLS/auth: local and demo delivery target Mailpit, which accepts
    plain SMTP on `settings.smtp_port`.
    """
    settings = get_settings()
    message = build_message(to=to, subject=subject, html=html, text=text, attachments=attachments)
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


async def deliver_outbox_email(
    db: AsyncSession,
    outbox_email: OutboxEmail,
    *,
    text: str | None = None,
    attachments: Sequence[EmailAttachment] = (),
) -> None:
    """CQ-020: sends an already-committed `QUEUED` outbox row and marks it
    `SENT` (flushes; the caller commits). Unlike `send_email`, a delivery
    failure marks the row `FAILED` and *re-raises*: the send workflow's
    Email activity wants Temporal to retry, and it commits the `QUEUED` row
    before calling this so a crash mid-send never loses the outbox record
    (plan.md Decision 8)."""
    try:
        await smtp_send(
            to=outbox_email.to_email,
            subject=outbox_email.subject,
            html=outbox_email.html,
            text=text,
            attachments=attachments,
        )
    except Exception:
        logger.exception("Failed to send email to %s", outbox_email.to_email)
        outbox_email.status = EmailStatus.FAILED
        await db.flush()
        raise
    outbox_email.status = EmailStatus.SENT
    await db.flush()
