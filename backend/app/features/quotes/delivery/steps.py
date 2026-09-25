"""The five `SendQuotePackage` steps as plain DB functions (CQ-020 spec).

`app/workflows/send_activities.py` wraps each in a Temporal activity that
opens its own session; tests call these directly too. Every step is
idempotent, keyed on the workflow id (plan.md Decision 8), so a Temporal
retry -- including one on a different worker after a crash -- never
duplicates a version, a PDF, an email or an event:

- `freeze` -- key: `quote_package_versions.send_workflow_id`. Writes the
  version (token, `sent_at`, `expires_at`) and the package's `sent_at`.
- `render_letter` -- key: the version's `letter_key` object exists. Writes
  the PDF to MinIO and `letter_key`.
- `email_borrower` -- key: the `outbox_email_id` row is `sent`. Writes the
  `outbox_emails` row, then SMTP.
- `record` -- key: a `quote.sent` activity event for the version. Writes
  status Sent, the activity event and the CRM event.

The spec's "Report link" step is `report_url(token)` below; the token is
minted by `freeze_package_version` (plan.md Decision 10).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import get_settings
from app.core.enums import ApplicationStatus
from app.core.errors import AppError
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.clients.models import Client
from app.features.notifications.email.service import EmailAttachment, deliver_outbox_email
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail
from app.features.portal.reports.versions import freeze_package_version
from app.features.quotes.delivery.email_template import render_borrower_email
from app.features.quotes.pdf.service import render_letter_pdf, render_package_letter
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion, SendStatus
from app.features.quotes.send.readiness import package_blockers
from app.integrations.crm.mock import MockCrmClient

SENT_EVENT_TYPE = "quote.sent"
"""Same activity-event type the seed's `apply_send_fixture` writes."""
CRM_EVENT_TYPE = "quote.sent"
LETTER_FILENAME = "preapproval-letter.pdf"
_ACTOR_SYSTEM = "system"


class PackageNotReadyError(AppError):
    """Freeze found blockers (plan.md Decision 12). Non-retryable: the
    workflow marks the send failed with this message."""

    code = "PACKAGE_NOT_READY"
    status_code = 409


def report_url(token: str) -> str:
    """H2: the email links to the sign-in-gated report, never a magic link."""
    return f"{get_settings().portal_base_url.rstrip('/')}/report/{token}"


def letter_key(package_id: uuid.UUID, version: int) -> str:
    """Per-version key (plan.md Decision 6) so a re-send never overwrites
    an older version's PDF."""
    return f"packages/{package_id}/v{version}/{LETTER_FILENAME}"


async def _set_step(
    db: AsyncSession, package_id: uuid.UUID, workflow_id: str, status: SendStatus
) -> None:
    """Writes `send_status` only while this workflow is the package's
    current send (a stale run never clobbers a newer one). Flushes."""
    await db.execute(
        update(QuotePackage)
        .where(QuotePackage.id == package_id, QuotePackage.send_workflow_id == workflow_id)
        .values(send_status=status.value, send_error=None)
    )


async def _version(db: AsyncSession, version_id: uuid.UUID) -> QuotePackageVersion:
    version = await db.get(QuotePackageVersion, version_id, populate_existing=True)
    if version is None:
        raise ValueError(f"QuotePackageVersion not found: {version_id}")
    return version


async def freeze(db: AsyncSession, package_id: uuid.UUID, workflow_id: str) -> uuid.UUID:
    """Step 1. Returns the version id; commits."""
    package = (
        await db.execute(
            select(QuotePackage)
            .where(QuotePackage.id == package_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    existing = (
        await db.execute(
            select(QuotePackageVersion.id).where(
                QuotePackageVersion.send_workflow_id == workflow_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    blockers = await package_blockers(db, package)
    if blockers:
        raise PackageNotReadyError("; ".join(b.message for b in blockers))

    await _set_step(db, package.id, workflow_id, SendStatus.RENDERING)
    version = await freeze_package_version(db, package=package, sent_at=datetime.now(UTC))
    version.send_workflow_id = workflow_id
    # M3 (plan.md Decision 2): the package's current content *is* the newest
    # sent version from here on; a later PUT reopens it as a draft.
    package.sent_at = version.sent_at
    package.expires_at = version.expires_at
    await db.flush()
    version_id = version.id
    await db.commit()
    return version_id


def _snapshot(version: QuotePackageVersion) -> dict[str, Any]:
    snapshot = version.snapshot
    assert isinstance(snapshot, dict)
    return snapshot


def _frozen_package(package: QuotePackage, snapshot: dict[str, Any]) -> QuotePackage:
    """A transient (never added to the session) package holding the
    snapshot's quotes, so the letter shows exactly what was frozen even if
    the working package changed after Freeze (plan.md Decision 11)."""
    options = snapshot.get("options") or []
    recommended = next((o["quote_id"] for o in options if o.get("recommended")), None)
    return QuotePackage(
        id=package.id,
        application_id=package.application_id,
        quote_ids=[uuid.UUID(o["quote_id"]) for o in options],
        recommended_quote_id=uuid.UUID(recommended) if recommended else None,
        lo_note=package.lo_note,
        recommendation_text=package.recommendation_text,
    )


async def render_letter(db: AsyncSession, version_id: uuid.UUID, workflow_id: str) -> str:
    """Step 2. Returns the MinIO key; commits."""
    version = await _version(db, version_id)
    package = await db.get(QuotePackage, version.package_id)
    assert package is not None
    key = letter_key(package.id, version.version)
    if version.letter_key == key and await storage.object_exists(key):
        return key

    await _set_step(db, package.id, workflow_id, SendStatus.RENDERING)
    html = await render_package_letter(
        db,
        _frozen_package(package, _snapshot(version)),
        portal_url=report_url(version.report_token),
        letter_date=version.sent_at.date(),
    )
    pdf = await asyncio.to_thread(render_letter_pdf, html)
    await storage.put_object(key, pdf, "application/pdf")
    version.letter_key = key
    package.letter_key = key
    await db.commit()
    return key


async def email_borrower(db: AsyncSession, version_id: uuid.UUID, workflow_id: str) -> uuid.UUID:
    """Step 4. Returns the outbox row id; commits the `queued` row before
    SMTP so a crash mid-send never loses it, then marks it `sent`."""
    version = await _version(db, version_id)
    package = await db.get(QuotePackage, version.package_id)
    assert package is not None
    if version.outbox_email_id is not None:
        outbox = await db.get(OutboxEmail, version.outbox_email_id, populate_existing=True)
        assert outbox is not None
        if outbox.status is EmailStatus.SENT:
            return outbox.id
    else:
        application = await db.get(Application, package.application_id)
        assert application is not None
        client_row = await db.get(Client, application.client_id)
        assert client_row is not None
        assert version.letter_key is not None, "render_letter runs before email_borrower"
        message = render_borrower_email(
            _snapshot(version), report_url=report_url(version.report_token)
        )
        outbox = OutboxEmail(
            to_email=client_row.email.strip(),
            subject=message.subject,
            html=message.html,
            attachment_keys=[version.letter_key],
            status=EmailStatus.QUEUED,
            application_id=application.id,
        )
        db.add(outbox)
        await db.flush()
        version.outbox_email_id = outbox.id
    await _set_step(db, package.id, workflow_id, SendStatus.EMAILING)
    await db.commit()

    assert version.letter_key is not None
    pdf = await storage.get_object(version.letter_key)
    if pdf is None:
        raise RuntimeError(f"Letter PDF missing in storage: {version.letter_key}")
    message = render_borrower_email(_snapshot(version), report_url=report_url(version.report_token))
    try:
        await deliver_outbox_email(
            db,
            outbox,
            text=message.text,
            attachments=[EmailAttachment(filename=LETTER_FILENAME, content=pdf)],
        )
    finally:
        await db.commit()
    return outbox.id


async def record(db: AsyncSession, version_id: uuid.UUID, workflow_id: str) -> None:
    """Step 5. Status Sent + one activity event + one CRM event, in one
    transaction; commits."""
    version = await _version(db, version_id)
    package = await db.get(QuotePackage, version.package_id)
    assert package is not None
    application = (
        await db.execute(
            select(Application)
            .where(Application.id == package.application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    already = (
        await db.execute(
            select(ActivityEvent.id).where(
                ActivityEvent.application_id == application.id,
                ActivityEvent.type == SENT_EVENT_TYPE,
                ActivityEvent.payload["version_id"].astext == str(version.id),
            )
        )
    ).first()
    if already is None:
        previous_status = application.status
        in_reply_to_inquiry = previous_status is ApplicationStatus.INQUIRY
        application.status = ApplicationStatus.SENT
        payload: dict[str, Any] = {
            "package_id": str(package.id),
            "version_id": str(version.id),
            "version": version.version,
            "sent_at": version.sent_at.isoformat(),
            "expires_at": version.expires_at.isoformat(),
            "letter_key": version.letter_key,
            "outbox_email_id": str(version.outbox_email_id) if version.outbox_email_id else None,
            "previous_status": previous_status.value,
            # plan.md Decision 3: the version <-> inquiry link CQ-024 asked for.
            "in_reply_to_inquiry": in_reply_to_inquiry,
        }
        db.add(
            ActivityEvent(
                application_id=application.id,
                actor=_ACTOR_SYSTEM,
                type=SENT_EVENT_TYPE,
                payload=payload,
                at=datetime.now(UTC),
            )
        )
        client_row = await db.get(Client, application.client_id)
        assert client_row is not None
        await MockCrmClient(db).log_event(
            client_row.crm_contact_id or str(client_row.id),
            CRM_EVENT_TYPE,
            {
                "application_id": str(application.id),
                "package_id": str(package.id),
                "version": version.version,
                "report_url": report_url(version.report_token),
                "in_reply_to_inquiry": in_reply_to_inquiry,
            },
        )
    await _set_step(db, package.id, workflow_id, SendStatus.DONE)
    await db.commit()


async def mark_failed(
    db: AsyncSession, package_id: uuid.UUID, workflow_id: str, message: str
) -> None:
    """The workflow's failure path: `send_status = failed` with the reason."""
    await db.execute(
        update(QuotePackage)
        .where(QuotePackage.id == package_id, QuotePackage.send_workflow_id == workflow_id)
        .values(send_status=SendStatus.FAILED.value, send_error=message[:500])
    )
    await db.commit()
