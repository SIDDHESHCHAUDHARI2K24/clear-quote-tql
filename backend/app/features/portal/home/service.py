"""`GET /api/v1/portal/me` (CQ-031 spec.md): the borrower's greeting and
one card per application, each reduced to a plain-language `stage`/`label`
and exactly one `next_action`.

`stage_and_label` is the *only* place the internal `ApplicationStatus` is
turned into borrower-facing text (spec.md "Notes for the agent") -- nothing
else in this module, and nothing on the frontend, re-derives it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.auth.models import BorrowerAccount, User
from app.features.borrower.consent.models import Consent, ConsentStatus
from app.features.clients.models import Client
from app.features.portal.apply.models import ApplicationDraft
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion

from .schemas import (
    PortalApplicationOut,
    PortalHomeResponse,
    PortalLoOut,
    PortalNextAction,
    PortalNextActionType,
    PortalStage,
)

_APPLIED_STATUSES = {
    ApplicationStatus.INTAKE,
    ApplicationStatus.VERIFYING,
    ApplicationStatus.NEEDS_ATTENTION,
    ApplicationStatus.READY_TO_PRICE,
}
_PREAPPROVED_STATUSES = {
    ApplicationStatus.SENT,
    ApplicationStatus.VIEWED,
    ApplicationStatus.INQUIRY,
}
_CLOSED_STATUSES = {ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED}

_LABEL_APPLIED = "Application received"
_LABEL_IN_REVIEW = "Your loan officer is reviewing your numbers"
_LABEL_PREAPPROVED = "Your pre-approval is ready"
_LABEL_CLOSED = "This application is closed"
_LABEL_DRAFT = "Continue your application"


def stage_and_label(
    status: ApplicationStatus, *, has_ever_sent: bool, lo_first_name: str
) -> tuple[PortalStage, str]:
    """Maps an internal `ApplicationStatus` to the borrower-facing
    `(stage, label)` pair from spec.md's table. `has_ever_sent` -- whether
    any `quote_package_versions` row exists for the application, sent or
    not superseded doesn't matter here -- is what splits `Stale (never
    sent)` from `Stale (after a send)`, since `ApplicationStatus.STALE`
    alone can't tell them apart.
    """
    if status in _APPLIED_STATUSES:
        return PortalStage.APPLIED, _LABEL_APPLIED
    if status is ApplicationStatus.PRICED:
        return PortalStage.IN_REVIEW, _LABEL_IN_REVIEW
    if status is ApplicationStatus.STALE:
        if has_ever_sent:
            return PortalStage.PREAPPROVED, _LABEL_PREAPPROVED
        return PortalStage.IN_REVIEW, _LABEL_IN_REVIEW
    if status in _PREAPPROVED_STATUSES:
        return PortalStage.PREAPPROVED, _LABEL_PREAPPROVED
    if status is ApplicationStatus.OPTION_SELECTED:
        label = f"You chose an option — {lo_first_name} will be in touch"
        return PortalStage.OPTION_SELECTED, label
    if status in _CLOSED_STATUSES:
        return PortalStage.CLOSED, _LABEL_CLOSED
    raise AssertionError(f"Unmapped ApplicationStatus: {status!r}")  # pragma: no cover


async def has_ever_sent(db: AsyncSession, *, application_id: uuid.UUID) -> bool:
    """Public (CQ-034 fix, post-dev.md review round 1): `portal/support/
    service.py` needs this to reuse `stage_and_label` instead of keeping
    its own status->stage table, so this is no longer module-private."""
    stmt = (
        select(QuotePackageVersion.id)
        .join(QuotePackage, QuotePackage.id == QuotePackageVersion.package_id)
        .where(QuotePackage.application_id == application_id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _latest_report_token(db: AsyncSession, *, application_id: uuid.UUID) -> str | None:
    """The newest non-superseded sent version's token, or `None` if the
    application was never sent (or every version has since been
    superseded)."""
    stmt = (
        select(QuotePackageVersion.report_token)
        .join(QuotePackage, QuotePackage.id == QuotePackageVersion.package_id)
        .where(
            QuotePackage.application_id == application_id,
            QuotePackageVersion.superseded.is_(False),
        )
        .order_by(QuotePackageVersion.version.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _pending_consent_id(db: AsyncSession, *, application_id: uuid.UUID) -> uuid.UUID | None:
    """The most recently requested still-valid pending consent. Filters
    out expired rows in the query itself (not just on the newest row) so
    an older, still-valid pending request isn't silently skipped if a
    newer pending row for the same application has since expired --
    nothing in the schema stops more than one PENDING row per
    application (review round 1 finding)."""
    moment = now()
    stmt = (
        select(Consent.id)
        .where(
            Consent.application_id == application_id,
            Consent.status == ConsentStatus.PENDING,
            (Consent.expires_at.is_(None)) | (Consent.expires_at > moment),
        )
        .order_by(Consent.requested_at.desc().nullslast())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _build_application_out(
    db: AsyncSession, application: Application
) -> PortalApplicationOut:
    lo = await db.get(User, application.lo_id)
    lo_first_name = lo.full_name.split()[0] if lo else ""
    ever_sent = await has_ever_sent(db, application_id=application.id)
    stage, label = stage_and_label(
        application.status, has_ever_sent=ever_sent, lo_first_name=lo_first_name
    )

    latest_token = await _latest_report_token(db, application_id=application.id)

    if stage is PortalStage.OPTION_SELECTED:
        next_action = PortalNextAction(type=PortalNextActionType.NONE)
        secondary_token = latest_token
    elif stage is PortalStage.CLOSED:
        next_action = PortalNextAction(type=PortalNextActionType.NONE)
        secondary_token = None
    else:
        consent_id = await _pending_consent_id(db, application_id=application.id)
        if consent_id is not None:
            next_action = PortalNextAction(
                type=PortalNextActionType.AUTHORIZE_CREDIT_CHECK, consent_id=consent_id
            )
        elif latest_token is not None:
            next_action = PortalNextAction(
                type=PortalNextActionType.VIEW_REPORT, report_token=latest_token
            )
        else:
            next_action = PortalNextAction(type=PortalNextActionType.NONE)
        secondary_token = None

    return PortalApplicationOut(
        id=application.id,
        stage=stage,
        label=label,
        next_action=next_action,
        secondary_report_token=secondary_token,
        lo=PortalLoOut(name=lo.full_name, phone=lo.phone, email=lo.email) if lo else None,
    )


async def _open_draft_out(
    db: AsyncSession, *, borrower_account_id: uuid.UUID
) -> PortalApplicationOut | None:
    draft = (
        await db.execute(
            select(ApplicationDraft).where(
                ApplicationDraft.borrower_account_id == borrower_account_id,
                ApplicationDraft.submitted_application_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if draft is None:
        return None
    return PortalApplicationOut(
        id=draft.id,
        stage=PortalStage.DRAFT,
        label=_LABEL_DRAFT,
        next_action=PortalNextAction(
            type=PortalNextActionType.CONTINUE_APPLICATION, draft_id=draft.id
        ),
        lo=None,
    )


async def get_home(db: AsyncSession, *, borrower: BorrowerAccount) -> PortalHomeResponse:
    client = await db.get(Client, borrower.client_id)
    first_name = client.full_name.split()[0] if client else ""

    applications = (
        (
            await db.execute(
                select(Application)
                .where(Application.client_id == borrower.client_id)
                .order_by(Application.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    items = [await _build_application_out(db, application) for application in applications]

    draft_out = await _open_draft_out(db, borrower_account_id=borrower.id)
    if draft_out is not None:
        items.insert(0, draft_out)

    return PortalHomeResponse(first_name=first_name, email=borrower.email, applications=items)
