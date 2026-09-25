"""Borrower decisions on hard-pull consent requests (CQ-033).

- `get_consent`: the request, the `hard_pull_v1` text and the requesting LO.
- `accept_consent`: records the signed decision, then runs the
  consent-gated `perform_hard_pull` in the same transaction and emails the
  LO. Idempotent under `lock_application` (AC6).
- `decline_consent`: records the decline and emails the LO; no pull (AC3).

Ownership is checked before anything else, so another borrower always
gets 404 (AC5, Decision #11). A pending request past `expires_at` is
persisted as `expired` whenever it is read (plan.md decision 7), by a
conditional UPDATE that never overwrites a decision (hardening m3).

Lock order on accept (hardening m1): the application's quotes
(`lock_application_quotes`, `FOR UPDATE`) and THEN `lock_application`,
the same order as CQ-030's `mark_stale` (quotes -> versions ->
applications), because the pull may UPDATE those quotes (E12). Decline
touches no quotes and takes only the application lock.

A provider failure (hardening m4) rolls the decision back, so the request
stays pending for a retry, then records `credit.hard_pull_failed` and
emails the LO in a separate transaction before re-raising.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ensure_borrower_owns_client
from app.core.clock import now
from app.core.config import get_settings
from app.core.errors import ConflictError, IntegrationError, NotFoundError, ValidationAppError
from app.features.applications.credit.hard_pull import (
    HARD_PULL_FAILED,
    HARD_PULL_SOURCE_REF,
    lock_application_quotes,
    perform_hard_pull,
)
from app.features.applications.locking import lock_application
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.sections import events
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import BorrowerAccount, User
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.clients.models import Client
from app.features.notifications.email.service import send_email

from . import templates
from .consent_text import HARD_PULL_TEXT_VERSION, consent_text_hash, hard_pull_text, split_text
from .schemas import ConsentLoOut, ConsentTextOut, PortalConsentOut

logger = logging.getLogger(__name__)

CONSENT_ACCEPTED = "credit.consent_accepted"
CONSENT_DECLINED = "credit.consent_declined"
BORROWER_ACTOR = "borrower"
USER_AGENT_MAX = 1000


class ConsentExpiredError(ConflictError):
    code = "CONSENT_EXPIRED"


class ConsentClosedError(ConflictError):
    code = "CONSENT_CLOSED"


class ConsentTextChangedError(ConflictError):
    code = "CONSENT_TEXT_CHANGED"


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


async def _load(
    db: AsyncSession, borrower: BorrowerAccount, consent_id: uuid.UUID
) -> tuple[Consent, Application]:
    consent = (
        await db.execute(
            select(Consent)
            .where(Consent.id == consent_id, Consent.type == ConsentType.HARD_PULL)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if consent is None:
        raise NotFoundError("Not found")
    application = await db.get(Application, consent.application_id)
    if application is None:
        raise NotFoundError("Not found")
    ensure_borrower_owns_client(borrower, application.client_id)
    return consent, application


async def _reload(db: AsyncSession, consent_id: uuid.UUID) -> Consent:
    return (
        await db.execute(
            select(Consent)
            .where(Consent.id == consent_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _expire_if_due(db: AsyncSession, consent: Consent) -> tuple[Consent, bool]:
    """Persists `expired` for a pending request past `expires_at`.

    The write is conditional on the row (hardening m3): `status = pending`
    and `expires_at <= now` in the UPDATE itself, so a decision committed
    after `consent` was read is never overwritten. Returns the re-read row
    and whether this call expired it."""
    if not (
        consent.status is ConsentStatus.PENDING
        and consent.expires_at is not None
        and consent.expires_at <= now()
    ):
        return consent, False
    result = await db.execute(
        update(Consent)
        .where(
            Consent.id == consent.id,
            Consent.status == ConsentStatus.PENDING,
            Consent.expires_at <= now(),
        )
        .values(status=ConsentStatus.EXPIRED)
        .execution_options(synchronize_session=False)
    )
    expired = bool(getattr(result, "rowcount", 0))
    if expired:
        logger.info("Consent %s expired unanswered", consent.id)
    return await _reload(db, consent.id), expired


async def _names(db: AsyncSession, application: Application) -> tuple[str, set[str]]:
    """(display name, accepted normalized names) for the typed signature."""
    party = (
        await db.execute(
            select(ApplicationParty).where(
                ApplicationParty.application_id == application.id,
                ApplicationParty.role == PartyRole.BORROWER,
            )
        )
    ).scalar_one_or_none()
    client = await db.get(Client, application.client_id)
    candidates: list[str] = []
    if party is not None and (party.first_name or party.last_name):
        candidates.append(f"{party.first_name or ''} {party.last_name or ''}".strip())
    if client is not None and client.full_name:
        candidates.append(client.full_name)
    display = candidates[0] if candidates else ""
    return display, {_norm_name(name) for name in candidates if _norm_name(name)}


async def _hard_pull_fico(db: AsyncSession, application_id: uuid.UUID) -> int | None:
    row = (
        await db.execute(
            select(FieldValue).where(
                FieldValue.application_id == application_id,
                FieldValue.field_key == "representative_fico",
            )
        )
    ).scalar_one_or_none()
    if row is None or row.source_ref != HARD_PULL_SOURCE_REF or row.value is None:
        return None
    try:
        return int(str(row.value))
    except ValueError:
        return None


async def _out(db: AsyncSession, consent: Consent, application: Application) -> PortalConsentOut:
    display, _ = await _names(db, application)
    lo_user = await db.get(User, consent.requested_by or application.lo_id)
    version = consent.text_version or HARD_PULL_TEXT_VERSION
    full_text = hard_pull_text(version)
    body, authorization = split_text(full_text)
    return PortalConsentOut(
        id=consent.id,
        application_id=application.id,
        status=consent.status,
        requested_at=consent.requested_at,
        expires_at=consent.expires_at,
        decided_at=consent.decided_at,
        decline_reason=consent.decline_reason,
        borrower_name=display,
        lo=(
            ConsentLoOut(
                name=lo_user.full_name, email=lo_user.email, phone=lo_user.phone, nmls=lo_user.nmls
            )
            if lo_user is not None
            else None
        ),
        text=ConsentTextOut(
            version=version,
            body=body,
            authorization=authorization,
            sha256=consent_text_hash(full_text),
        ),
        fico_after_pull=(
            await _hard_pull_fico(db, application.id)
            if consent.status is ConsentStatus.ACCEPTED
            else None
        ),
    )


def _credit_tab_link(application_id: uuid.UUID) -> str:
    base = get_settings().lo_console_base_url.rstrip("/")
    return f"{base}/applications/{application_id}/credit"


async def _lo_email(db: AsyncSession, application: Application) -> str | None:
    lo_user = await db.get(User, application.lo_id)
    return lo_user.email if lo_user is not None else None


async def get_consent(
    db: AsyncSession, *, borrower: BorrowerAccount, consent_id: uuid.UUID
) -> PortalConsentOut:
    consent, application = await _load(db, borrower, consent_id)
    consent, expired = await _expire_if_due(db, consent)
    if expired:
        await db.commit()
    return await _out(db, consent, application)


async def _open_for_decision(
    db: AsyncSession,
    borrower: BorrowerAccount,
    consent_id: uuid.UUID,
    *,
    lock_quotes: bool = False,
) -> tuple[Consent, Application]:
    """Ownership, then the locks (quotes first when asked, then the
    application; see the module docstring), then a fresh read of the row."""
    consent, application = await _load(db, borrower, consent_id)
    if lock_quotes:
        await lock_application_quotes(db, application.id)
    await lock_application(db, application.id)
    return await _reload(db, consent.id), application


async def _ensure_pending(db: AsyncSession, consent: Consent) -> None:
    consent, expired = await _expire_if_due(db, consent)
    if expired:
        await db.commit()
        raise ConsentExpiredError("This credit-check request has expired.")
    if consent.status is ConsentStatus.EXPIRED:
        raise ConsentExpiredError("This credit-check request has expired.")
    if consent.status is not ConsentStatus.PENDING:
        raise ConsentClosedError(f"This credit-check request was already {consent.status.value}.")


async def accept_consent(
    db: AsyncSession,
    *,
    borrower: BorrowerAccount,
    consent_id: uuid.UUID,
    typed_name: str,
    text_version: str,
    text_sha256: str,
    ip: str | None,
    user_agent: str | None,
) -> PortalConsentOut:
    consent, application = await _open_for_decision(db, borrower, consent_id, lock_quotes=True)
    if consent.status is ConsentStatus.ACCEPTED:
        # AC6: a repeat accept returns the recorded decision; no second pull.
        return await _out(db, consent, application)
    await _ensure_pending(db, consent)

    full_text = hard_pull_text(HARD_PULL_TEXT_VERSION)
    text_hash = consent_text_hash(full_text)
    if text_version != HARD_PULL_TEXT_VERSION or text_sha256 != text_hash:
        # m2: the stored hash must be the text the borrower actually saw.
        raise ConsentTextChangedError(
            "The authorization text has changed since you opened it. Review it and try again."
        )

    display, accepted_names = await _names(db, application)
    if _norm_name(typed_name) not in accepted_names:
        raise ValidationAppError(
            "The typed name must match your full name on the application.",
            code="NAME_MISMATCH",
        )

    decided = now()
    consent.status = ConsentStatus.ACCEPTED
    consent.text_version = HARD_PULL_TEXT_VERSION
    consent.text_hash = text_hash
    consent.typed_name = " ".join(typed_name.split())
    consent.ip = ip
    consent.user_agent = user_agent[:USER_AGENT_MAX] if user_agent else None
    consent.decided_at = decided
    consent.at = decided
    await db.flush()
    events.add_event(
        db,
        application.id,
        actor=BORROWER_ACTOR,
        type=CONSENT_ACCEPTED,
        payload={
            "consent_id": str(consent.id),
            "text_version": HARD_PULL_TEXT_VERSION,
            "message": "Borrower authorized the hard credit pull",
        },
    )

    application_id = application.id
    lo_email = await _lo_email(db, application)
    try:
        result = await perform_hard_pull(db, application_id, consent_id=consent.id)
    except IntegrationError as exc:
        await _record_pull_failure(
            db,
            application_id=application_id,
            consent_id=consent.id,
            borrower_name=display,
            lo_email=lo_email,
            error_code=exc.code,
        )
        raise

    if lo_email:
        await send_email(
            db,
            to=lo_email,
            subject=templates.authorized_subject(result.fico),
            html=templates.authorized_html(
                borrower_name=display, fico=result.fico, link=_credit_tab_link(application.id)
            ),
            application_id=application.id,
        )
    await db.commit()
    return await _out(db, consent, application)


async def _record_pull_failure(
    db: AsyncSession,
    *,
    application_id: uuid.UUID,
    consent_id: uuid.UUID,
    borrower_name: str,
    lo_email: str | None,
    error_code: str,
) -> None:
    """m4: the bureau failed. Roll the decision back (the request stays
    pending, so the borrower can retry), then write the failure event and
    the LO email in their own transaction.

    The LO is emailed once per consent, not on every retry (review low 2).
    Best effort (review low 1): a failure here is logged and swallowed, so
    the caller still re-raises the bureau error, not this one."""
    await db.rollback()
    logger.warning(
        "Hard pull for application %s (consent %s) failed: %s",
        application_id,
        consent_id,
        error_code,
    )
    try:
        already_told = (
            await db.execute(
                select(ActivityEvent.id)
                .where(
                    ActivityEvent.application_id == application_id,
                    ActivityEvent.type == HARD_PULL_FAILED,
                    ActivityEvent.payload["consent_id"].astext == str(consent_id),
                )
                .limit(1)
            )
        ).scalar_one_or_none() is not None
        events.add_event(
            db,
            application_id,
            actor=events.SYSTEM_ACTOR,
            type=HARD_PULL_FAILED,
            payload={
                "consent_id": str(consent_id),
                "error_code": error_code,
                "message": "Hard credit pull could not be completed; the request stays open",
            },
        )
        if lo_email and not already_told:
            await send_email(
                db,
                to=lo_email,
                subject=templates.failed_subject(),
                html=templates.failed_html(
                    borrower_name=borrower_name, link=_credit_tab_link(application_id)
                ),
                application_id=application_id,
            )
        await db.commit()
    except Exception:
        logger.exception(
            "Could not record the failed hard pull for application %s (consent %s)",
            application_id,
            consent_id,
        )
        await db.rollback()


async def decline_consent(
    db: AsyncSession,
    *,
    borrower: BorrowerAccount,
    consent_id: uuid.UUID,
    reason: str | None,
) -> PortalConsentOut:
    consent, application = await _open_for_decision(db, borrower, consent_id)
    await _ensure_pending(db, consent)

    cleaned = " ".join(reason.split()) if reason else None
    consent.status = ConsentStatus.DECLINED
    consent.decline_reason = cleaned or None
    consent.decided_at = now()
    await db.flush()
    events.add_event(
        db,
        application.id,
        actor=BORROWER_ACTOR,
        type=CONSENT_DECLINED,
        payload={
            "consent_id": str(consent.id),
            "message": "Borrower declined the hard credit pull",
        },
    )
    display, _ = await _names(db, application)
    lo_email = await _lo_email(db, application)
    if lo_email:
        await send_email(
            db,
            to=lo_email,
            subject=templates.declined_subject(),
            html=templates.declined_html(
                borrower_name=display,
                reason=consent.decline_reason,
                link=_credit_tab_link(application.id),
            ),
            application_id=application.id,
        )
    await db.commit()
    return await _out(db, consent, application)
