"""Credit-tab actions: "Import liabilities" (AC4) and "Request hard pull"
(AC5, E11). Nothing here commits.
"""

from __future__ import annotations

import html
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.features.applications.credit.models import Liability
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.sections import events, provenance
from app.features.applications.sections.service import (
    effective_consent_status,
    latest_consent,
)
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.clients.models import Client
from app.features.notifications.email.service import send_email
from app.integrations.los.mock import MockLosClient
from app.integrations.los.schemas import LoanFileDTO

CONSENT_TTL = timedelta(days=14)


async def fetch_loan_file(db: AsyncSession, application: Application) -> LoanFileDTO:
    """Reads the application's loan file from the (mock) LOS. Call it before
    taking the application lock: the provider call can be slow
    (lock-hardening minor 2)."""
    if not application.los_loan_guid:
        raise ValidationAppError("This application has no LOS loan to import liabilities from.")
    return await MockLosClient(db).get_loan_file(application.los_loan_guid)


async def import_liabilities(
    db: AsyncSession, application: Application, user_id: uuid.UUID, loan_file: LoanFileDTO
) -> None:
    """Replaces every imported liability with `loan_file`'s current list
    (from `fetch_loan_file`) and keeps LO-added rows (plan.md #15). Runs
    under the application lock."""
    manual = await provenance.load_manual_rows(db, application.id)
    rows = (
        (await db.execute(select(Liability).where(Liability.application_id == application.id)))
        .scalars()
        .all()
    )
    removed = kept = 0
    for row in rows:
        if provenance.row_marker_key("liabilities", row.id) in manual:
            kept += 1
            continue
        await provenance.delete_row_provenance(db, application.id, "liabilities", row.id)
        await db.delete(row)
        removed += 1
    for dto in loan_file.liabilities:
        db.add(
            Liability(
                application_id=application.id,
                creditor_name=dto.creditor_name,
                account_type=dto.account_type,
                monthly_payment=dto.monthly_payment,
                balance=dto.balance,
            )
        )
    await db.flush()
    events.add_event(
        db,
        application.id,
        actor=events.actor_for(user_id),
        type=events.LIABILITIES_IMPORTED,
        payload={
            "imported": len(loan_file.liabilities),
            "replaced": removed,
            "kept_manual": kept,
            "message": (
                f"Imported {len(loan_file.liabilities)} liabilities from Encompass; "
                f"kept {kept} added by the LO"
            ),
        },
    )


def hard_pull_request_subject() -> str:
    return "Please authorize a credit check for your loan"


def hard_pull_request_html(*, first_name: str, link: str, expires_on: str) -> str:
    name = html.escape(first_name)
    href = html.escape(link, quote=True)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="font-family:-apple-system,Helvetica,Arial,sans-serif;">'
        '<tr><td style="padding:24px;color:#0f1b33;font-size:14px;">'
        f"<p>Hi {name},</p>"
        "<p>Your loan officer is ready to finalize your pre-approval and needs your "
        "permission for a hard credit check.</p>"
        f'<p><a href="{href}" style="color:#1d4ed8;">Review and authorize the credit check</a></p>'
        f'<p style="color:#5b6472;font-size:12px;">Or open this link: {href}</p>'
        f'<p style="color:#5b6472;font-size:12px;">This request expires on {expires_on}. '
        "If you did not expect it, you can decline on the same page.</p>"
        "</td></tr></table>"
    )


async def request_hard_pull(
    db: AsyncSession, application: Application, user_id: uuid.UUID
) -> Consent:
    """Creates one pending hard-pull consent request and emails the borrower.
    409 while a pending, unexpired request exists (AC5)."""
    # Serialize concurrent requests for the same application.
    await db.execute(
        select(Application.id).where(Application.id == application.id).with_for_update()
    )
    existing = await latest_consent(db, application.id)
    if existing is not None and effective_consent_status(existing) is ConsentStatus.PENDING:
        raise ConflictError("A hard-pull consent request is already pending for this borrower.")

    client = await db.get(Client, application.client_id)
    if client is None:
        raise NotFoundError("Client not found for this application.")
    primary = (
        await db.execute(
            select(ApplicationParty).where(
                ApplicationParty.application_id == application.id,
                ApplicationParty.role == PartyRole.BORROWER,
            )
        )
    ).scalar_one_or_none()
    first_name = primary.first_name if primary is not None else client.full_name.split(" ")[0]

    requested_at = now()
    consent = Consent(
        application_id=application.id,
        type=ConsentType.HARD_PULL,
        status=ConsentStatus.PENDING,
        requested_by=user_id,
        requested_at=requested_at,
        expires_at=requested_at + CONSENT_TTL,
    )
    db.add(consent)
    await db.flush()

    base_url = get_settings().portal_base_url.rstrip("/")
    link = f"{base_url}/tasks/credit-check/{consent.id}"
    await send_email(
        db,
        to=client.email,
        subject=hard_pull_request_subject(),
        html=hard_pull_request_html(
            first_name=first_name,
            link=link,
            expires_on=(requested_at + CONSENT_TTL).strftime("%B %d, %Y"),
        ),
        application_id=application.id,
    )
    events.add_event(
        db,
        application.id,
        actor=events.actor_for(user_id),
        type=events.HARD_PULL_REQUESTED,
        payload={
            "consent_id": str(consent.id),
            "message": "Requested borrower consent for a hard credit pull",
        },
    )
    return consent
