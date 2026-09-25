"""AC1: `send_email` writes an `outbox_emails` row and delivers over SMTP.

`send_email` always writes the outbox row first, then calls `smtp_send` (a
module-level seam so it can be monkeypatched without a live SMTP server) and
marks the row `SENT` or `FAILED` — it never raises, so a down SMTP server
never breaks the caller (e.g. the OTP-issue endpoint still returns).
`test_smtp_send_builds_message` checks the actual MIME message `smtp_send`
builds by monkeypatching `aiosmtplib.send` instead.
"""

import uuid
from email.message import EmailMessage

import aiosmtplib
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.notifications.email import service
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail


async def _make_application(db_session: AsyncSession) -> uuid.UUID:
    """Minimal valid `Application` row so an `application_id` FK resolves."""
    lo = User(
        email=f"lo-{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()

    client = Client(
        full_name="Test Client",
        email=f"client-{uuid.uuid4()}@example.com",
        assigned_lo_id=lo.id,
    )
    db_session.add(client)
    await db_session.flush()

    application = Application(client_id=client.id, lo_id=lo.id, occupancy=Occupancy.PRIMARY)
    db_session.add(application)
    await db_session.flush()
    return application.id


async def test_send_email_success_writes_sent_row_and_calls_smtp_send(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, str]] = []

    async def _fake_smtp_send(*, to: str, subject: str, html: str) -> None:
        calls.append({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr(service, "smtp_send", _fake_smtp_send)

    outbox_email = await service.send_email(
        db_session, to="lo@clearquote.test", subject="Your code", html="<p>123456</p>"
    )

    assert outbox_email.status == EmailStatus.SENT
    assert calls == [{"to": "lo@clearquote.test", "subject": "Your code", "html": "<p>123456</p>"}]

    row = (
        await db_session.execute(select(OutboxEmail).where(OutboxEmail.id == outbox_email.id))
    ).scalar_one()
    assert row.status == EmailStatus.SENT
    assert row.to_email == "lo@clearquote.test"
    assert row.subject == "Your code"
    assert row.html == "<p>123456</p>"


async def test_send_email_failure_marks_row_failed_and_does_not_raise(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _raising_smtp_send(*, to: str, subject: str, html: str) -> None:
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(service, "smtp_send", _raising_smtp_send)

    outbox_email = await service.send_email(
        db_session, to="lo@clearquote.test", subject="Your code", html="<p>123456</p>"
    )

    assert outbox_email.status == EmailStatus.FAILED

    row = (
        await db_session.execute(select(OutboxEmail).where(OutboxEmail.id == outbox_email.id))
    ).scalar_one()
    assert row.status == EmailStatus.FAILED


async def test_send_email_persists_application_id(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_smtp_send(*, to: str, subject: str, html: str) -> None:
        return None

    monkeypatch.setattr(service, "smtp_send", _fake_smtp_send)
    application_id = await _make_application(db_session)

    outbox_email = await service.send_email(
        db_session,
        to="lo@clearquote.test",
        subject="Your code",
        html="<p>123456</p>",
        application_id=application_id,
    )

    assert outbox_email.application_id == application_id

    row = (
        await db_session.execute(select(OutboxEmail).where(OutboxEmail.id == outbox_email.id))
    ).scalar_one()
    assert row.application_id == application_id


async def test_smtp_send_builds_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[EmailMessage] = []

    async def _fake_aiosmtplib_send(message: EmailMessage, **kwargs: object) -> None:
        sent.append(message)

    monkeypatch.setattr(aiosmtplib, "send", _fake_aiosmtplib_send)

    await service.smtp_send(to="borrower@clearquote.test", subject="Hi", html="<p>Hello</p>")

    message = sent[0]
    assert message["To"] == "borrower@clearquote.test"
    assert message["Subject"] == "Hi"
    assert message["From"]

    assert message.is_multipart()
    content_types = {part.get_content_type() for part in message.iter_parts()}
    assert "text/plain" in content_types
    assert "text/html" in content_types
