"""`POST /api/v1/portal/support` (CQ-034 spec.md): a borrower reaches
support -- one `support_requests` row, one email to `settings.support_inbox`
with the borrower's context (name, contact, message, latest application,
assigned LO), one short confirmation email back to the borrower, and one
activity event when there's an application to attach it to. Rate-limited to
5 requests/borrower/hour (Valkey).
"""

from __future__ import annotations

import secrets
import uuid

from redis.asyncio import Redis
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import ApplicationStatus
from app.core.errors import RateLimitedError
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import BorrowerAccount, User
from app.features.auth.otp.rate_limit import hit
from app.features.clients.models import Client
from app.features.notifications.email.service import send_email
from app.features.quotes.send.models import QuotePackage

from . import templates
from .models import SupportRequest
from .schemas import SupportLoContact, SupportRequestCreate, SupportRequestResponse

_ACTOR_SYSTEM = "system"
_ACTIVITY_EVENT_TYPE = "support.requested"

# "Unambiguous characters" (spec.md): excludes 0/O, 1/I/L.
_REFERENCE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_REFERENCE_SUFFIX_LENGTH = 5
_MAX_REFERENCE_ATTEMPTS = 10

_RATE_LIMIT_KEY_PREFIX = "rl:support:borrower"
_RATE_LIMIT_LIMIT = 5
_RATE_LIMIT_WINDOW_SECONDS = 3600
# AC4's exact wording -- distinct from `hit`'s own default message ("Too
# many attempts. Try again later."); no edit to the shared
# `otp/rate_limit.py` needed (plan.md Decision #5).
_RATE_LIMIT_MESSAGE = "Please try again later"

# CQ-031's status -> stage table (spec.md), duplicated here because
# `features/portal/home/` (CQ-031) hasn't merged into `phase-p5-p6` yet.
# Follow-up (plan.md Decision #1): switch this call site to CQ-031's
# canonical function once it lands, and delete this copy.
_STAGE_LABELS: dict[str, str] = {
    "applied": "Application received",
    "in_review": "Your loan officer is reviewing your numbers",
    "preapproved": "Your pre-approval is ready",
    "option_selected": "You chose an option",
    "closed": "This application is closed",
}

_STATUS_TO_STAGE_KEY: dict[ApplicationStatus, str] = {
    ApplicationStatus.INTAKE: "applied",
    ApplicationStatus.VERIFYING: "applied",
    ApplicationStatus.NEEDS_ATTENTION: "applied",
    ApplicationStatus.READY_TO_PRICE: "applied",
    ApplicationStatus.PRICED: "in_review",
    # STALE splits on whether the application was ever sent -- resolved
    # by the caller (see `_stage_key_for`) since it needs a DB query.
    ApplicationStatus.SENT: "preapproved",
    ApplicationStatus.VIEWED: "preapproved",
    ApplicationStatus.INQUIRY: "preapproved",
    ApplicationStatus.OPTION_SELECTED: "option_selected",
    ApplicationStatus.WITHDRAWN: "closed",
    ApplicationStatus.CLOSED: "closed",
}


async def _stage_key_for(db: AsyncSession, application: Application) -> str:
    if application.status is not ApplicationStatus.STALE:
        return _STATUS_TO_STAGE_KEY[application.status]
    ever_sent = (
        await db.execute(
            select(
                exists().where(
                    QuotePackage.application_id == application.id,
                    QuotePackage.sent_at.isnot(None),
                )
            )
        )
    ).scalar_one()
    return "preapproved" if ever_sent else "in_review"


def _generate_reference() -> str:
    suffix = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(_REFERENCE_SUFFIX_LENGTH))
    return f"SUP-{suffix}"


def _property_label(prop: Property | None) -> str | None:
    """`None` renders as "Property to be determined" (templates.py) --
    local copy of `portal/reports/versions.py::_property_label` (same
    "feature-local helper, not a cross-feature private import" reasoning
    as `templates.py`'s `_shell`)."""
    if prop is None or prop.address_status is PropertyAddressStatus.TBD:
        return None
    city_state_zip = " ".join(p for p in (prop.state, prop.zip) if p)
    pieces = [p for p in (prop.street_address, prop.city, city_state_zip) if p]
    return ", ".join(pieces) if pieces else None


async def _insert_with_unique_reference(
    db: AsyncSession,
    *,
    borrower_account_id: uuid.UUID,
    application_id: uuid.UUID | None,
    topic: str,
    message: str,
    preferred_contact: str,
    phone: str | None,
) -> SupportRequest:
    """Generates a reference and inserts the row inside a SAVEPOINT,
    retrying on a unique-constraint collision (spec.md: "retry on
    collision") -- same pattern as `auth/users/service.py::_insert_user`.
    """
    for _ in range(_MAX_REFERENCE_ATTEMPTS):
        support_request = SupportRequest(
            reference=_generate_reference(),
            borrower_account_id=borrower_account_id,
            application_id=application_id,
            topic=topic,
            message=message,
            preferred_contact=preferred_contact,
            phone=phone,
        )
        try:
            async with db.begin_nested():
                db.add(support_request)
                await db.flush()
        except IntegrityError:
            continue
        return support_request
    raise RuntimeError("Could not generate a unique support reference")


async def submit_support_request(
    db: AsyncSession,
    valkey: Redis,
    *,
    borrower: BorrowerAccount,
    request: SupportRequestCreate,
) -> SupportRequestResponse:
    try:
        await hit(
            valkey,
            f"{_RATE_LIMIT_KEY_PREFIX}:{borrower.id}",
            limit=_RATE_LIMIT_LIMIT,
            window_seconds=_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RateLimitedError:
        raise RateLimitedError(_RATE_LIMIT_MESSAGE) from None

    settings = get_settings()

    client_row = await db.get(Client, borrower.client_id)
    assert client_row is not None  # borrower_accounts.client_id is NOT NULL + FK-enforced

    lo = await db.get(User, client_row.assigned_lo_id)
    assert lo is not None

    application = (
        await db.execute(
            select(Application)
            .where(Application.client_id == borrower.client_id)
            .order_by(Application.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    stage_label: str | None = None
    property_label: str | None = None
    lo_console_url: str | None = None
    if application is not None:
        stage_key = await _stage_key_for(db, application)
        stage_label = _STAGE_LABELS[stage_key]
        property_row = (
            await db.execute(select(Property).where(Property.application_id == application.id))
        ).scalar_one_or_none()
        property_label = _property_label(property_row)
        lo_console_url = f"{settings.lo_console_base_url}/applications/{application.id}"

    support_request = await _insert_with_unique_reference(
        db,
        borrower_account_id=borrower.id,
        application_id=application.id if application is not None else None,
        topic=request.topic.value,
        message=request.message,
        preferred_contact=request.preferred_contact.value,
        phone=request.phone,
    )
    reference = support_request.reference

    inbox_subject = templates.support_inbox_subject(
        reference=reference, topic=request.topic.value, borrower_name=client_row.full_name
    )
    inbox_html = templates.support_inbox_html(
        reference=reference,
        borrower_name=client_row.full_name,
        borrower_email=client_row.email,
        phone=request.phone,
        preferred_contact=request.preferred_contact.value,
        message=request.message,
        application_id=str(application.id) if application is not None else None,
        stage_label=stage_label,
        internal_status=application.status.value if application is not None else None,
        property_label=property_label,
        lo_name=lo.full_name,
        lo_console_url=lo_console_url,
    )
    await send_email(
        db,
        to=settings.support_inbox,
        subject=inbox_subject,
        html=inbox_html,
        application_id=application.id if application is not None else None,
    )

    if application is not None:
        db.add(
            ActivityEvent(
                application_id=application.id,
                actor=_ACTOR_SYSTEM,
                type=_ACTIVITY_EVENT_TYPE,
                payload={"reference": reference, "topic": request.topic.value},
                at=now(),
            )
        )

    confirmation_subject = templates.confirmation_subject(reference)
    confirmation_html = templates.confirmation_html(
        borrower_name=client_row.full_name, reference=reference
    )
    await send_email(
        db,
        to=client_row.email,
        subject=confirmation_subject,
        html=confirmation_html,
        application_id=application.id if application is not None else None,
    )

    await db.commit()

    return SupportRequestResponse(
        reference=reference,
        lo=SupportLoContact(name=lo.full_name, email=lo.email, phone=lo.phone),
    )
