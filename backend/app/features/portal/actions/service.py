"""`POST /api/v1/portal/reports/{token}/actions` (CQ-024 spec.md): the
borrower says "move forward", "ask about another option" or (once
expired) "ask for updated numbers". Every action writes one
`ActivityEvent`, one LO email (`outbox_emails` + SMTP), and one mock CRM
event, then returns the new state so the caller doesn't have to guess.

Non-binding, always (system-design.md's Application status machine note,
Decision 5): this never locks a rate or accepts anything on the
borrower's behalf -- see `templates.py`'s own AC5 note and
`tests/test_templates.py::test_no_binding_language`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ensure_borrower_owns_client
from app.core.enums import ApplicationStatus
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import BorrowerAccount, User
from app.features.clients.models import Client
from app.features.notifications.email.service import send_email
from app.features.quotes.send.models import BorrowerAction, QuotePackage, QuotePackageVersion
from app.integrations.crm.mock import MockCrmClient

from . import templates
from .schemas import (
    BorrowerActionType,
    PortalReportActionRequest,
    PortalReportActionResponse,
)

_ACTOR_SYSTEM = "system"

_OPEN_STATUSES = {
    ApplicationStatus.SENT,
    ApplicationStatus.VIEWED,
    ApplicationStatus.INQUIRY,
}

# PR #8 review round 1 (MAJOR): `ask_updated` only checked `expired`, so an
# expired version whose application had already reached one of these
# terminal-for-this-item statuses (a `move_forward` elsewhere, or an LO
# withdrawing/closing the file) could still be resurrected back to
# `inquiry`. These are every status outside `_OPEN_STATUSES` that isn't
# itself an input to the machine (`stale` is a pipeline-only status that
# never reaches this endpoint's `Application`, since a report can't be sent
# for one -- excluded here rather than silently treated as blocking).
_TERMINAL_STATUSES = {
    ApplicationStatus.OPTION_SELECTED,
    ApplicationStatus.WITHDRAWN,
    ApplicationStatus.CLOSED,
}

# Shared between the `ask_updated`-vs-`_TERMINAL_STATUSES` check and the
# move_forward/ask_other-vs-`_OPEN_STATUSES` check below (code-review nit,
# PR #8 round 1) so the two 409 wordings can't silently drift apart.
_ALREADY_ACTED_ON_MESSAGE = "This option has already been acted on."

_ACTIVITY_EVENT_TYPE = {
    BorrowerActionType.MOVE_FORWARD: "quote.move_forward",
    BorrowerActionType.ASK_OTHER: "quote.ask_other",
    BorrowerActionType.ASK_UPDATED: "quote.ask_updated",
}


def _current_state(application: Application, version: QuotePackageVersion) -> dict[str, Any]:
    borrower_action = version.borrower_action
    assert borrower_action is None or isinstance(borrower_action, dict)
    return {"status": application.status.value, "borrower_action": borrower_action}


def _option_label(version: QuotePackageVersion, quote_id: str | None) -> str | None:
    if quote_id is None:
        return None
    snapshot = version.snapshot
    assert isinstance(snapshot, dict)
    for option in snapshot.get("options", []):
        if option.get("quote_id") == quote_id:
            return option.get("label")
    return None


def _validate_quote_id(version: QuotePackageVersion, quote_id: str) -> None:
    snapshot = version.snapshot
    assert isinstance(snapshot, dict)
    valid_ids = {option.get("quote_id") for option in snapshot.get("options", [])}
    if quote_id not in valid_ids:
        raise ValidationAppError("quote_id is not one of this report's options")


async def submit_action(
    db: AsyncSession,
    *,
    token: str,
    borrower: BorrowerAccount,
    request: PortalReportActionRequest,
) -> PortalReportActionResponse:
    # Lock package -> version -> application, in that order -- not the
    # token-lookup order (version -> package -> application) this
    # function's own flow would naturally suggest. Fresh-subagent review
    # finding: `versions.py::freeze_package_version` (CQ-020's future send/
    # resend path) locks `QuotePackage` first, then later locks existing
    # `QuotePackageVersion` rows via its `UPDATE ... SET superseded=True`.
    # Locking version-then-package here was the *opposite* order, so a
    # borrower's action racing a resend of the same package could deadlock
    # (Postgres aborts one side with a raw 500 instead of a clean 409).
    # `report_token` -> `package_id` is immutable once a version row
    # exists, so an unlocked lookup for it is safe -- the actual locked
    # re-read of the version row below (after the package lock) is what
    # matters for correctness, not this first lookup.
    package_id = (
        await db.execute(
            select(QuotePackageVersion.package_id).where(QuotePackageVersion.report_token == token)
        )
    ).scalar_one_or_none()
    if package_id is None:
        raise NotFoundError("Report not found")

    package = (
        await db.execute(
            select(QuotePackage).where(QuotePackage.id == package_id).with_for_update()
        )
    ).scalar_one_or_none()
    if package is None:
        raise NotFoundError("Report not found")

    version = (
        await db.execute(
            select(QuotePackageVersion)
            .where(QuotePackageVersion.report_token == token)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if version is None:
        raise NotFoundError("Report not found")

    application = (
        await db.execute(
            select(Application).where(Application.id == package.application_id).with_for_update()
        )
    ).scalar_one_or_none()
    if application is None:
        raise NotFoundError("Report not found")

    # 404 (never 403), identical message to `portal/reports/service.py`'s
    # own two 404 paths (CQ-024 review carry-over finding #1).
    try:
        ensure_borrower_owns_client(borrower, application.client_id)
    except NotFoundError:
        raise NotFoundError("Report not found") from None

    now = datetime.now(UTC)
    expired = now > version.expires_at

    # Superseded blocks every action type (plan.md Decision 3): the
    # frontend hides the whole slot in this case (SupersededBanner points
    # at the newest version instead), so this is defense in depth.
    if version.superseded:
        raise ConflictError(
            "This report has been replaced by a newer version.",
            details=_current_state(application, version),
        )

    action_type = request.type

    if action_type is BorrowerActionType.ASK_UPDATED:
        if not expired:
            raise ConflictError(
                "This report hasn't expired yet.", details=_current_state(application, version)
            )
        if application.status in _TERMINAL_STATUSES:
            raise ConflictError(
                _ALREADY_ACTED_ON_MESSAGE,
                details=_current_state(application, version),
            )
    else:
        if expired:
            raise ConflictError(
                "This report has expired.", details=_current_state(application, version)
            )
        if application.status not in _OPEN_STATUSES:
            raise ConflictError(
                _ALREADY_ACTED_ON_MESSAGE,
                details=_current_state(application, version),
            )

    if action_type is BorrowerActionType.MOVE_FORWARD:
        if not request.quote_id:
            raise ValidationAppError("quote_id is required for move_forward")
        _validate_quote_id(version, request.quote_id)

    if action_type is BorrowerActionType.ASK_OTHER:
        ask_other_message = (request.message or "").strip()
        if not (1 <= len(ask_other_message) <= 500):
            raise ValidationAppError("message must be between 1 and 500 characters")
        if request.quote_id is not None:
            _validate_quote_id(version, request.quote_id)

    if action_type is BorrowerActionType.ASK_UPDATED and request.quote_id is not None:
        _validate_quote_id(version, request.quote_id)

    client_row = await db.get(Client, application.client_id)
    assert client_row is not None
    lo = await db.get(User, application.lo_id)
    assert lo is not None

    option_label = _option_label(version, request.quote_id)
    message = request.message.strip() if request.message else None

    # Effect: application status + the two `borrower_action` copies
    # (Decision 1 -- the version's JSONB is the source of truth; the
    # package's coarse enum is a mirror).
    if action_type is BorrowerActionType.MOVE_FORWARD:
        application.status = ApplicationStatus.OPTION_SELECTED
        package.borrower_action = BorrowerAction.OPTION_SELECTED
    else:
        application.status = ApplicationStatus.INQUIRY
        package.borrower_action = BorrowerAction.INQUIRY

    version.borrower_action = {
        "type": action_type.value,
        "quote_id": request.quote_id,
        "message": message,
        "at": now.isoformat(),
    }

    db.add(
        ActivityEvent(
            application_id=application.id,
            actor=_ACTOR_SYSTEM,
            type=_ACTIVITY_EVENT_TYPE[action_type],
            payload={"quote_id": request.quote_id, "message": message},
            at=now,
        )
    )

    subject, html = _render_email(
        action_type,
        borrower_name=client_row.full_name,
        borrower_email=client_row.email,
        option_label=option_label,
        message=message,
    )
    await send_email(db, to=lo.email, subject=subject, html=html, application_id=application.id)

    contact_id = client_row.crm_contact_id or str(client_row.id)
    await MockCrmClient(db).log_event(
        contact_id,
        f"borrower.{action_type.value}",
        {
            "application_id": str(application.id),
            "quote_id": request.quote_id,
            "message": message,
        },
    )

    await db.commit()

    return PortalReportActionResponse(
        status=application.status,
        borrower_action=version.borrower_action,
        at=now,
    )


def _render_email(
    action_type: BorrowerActionType,
    *,
    borrower_name: str,
    borrower_email: str,
    option_label: str | None,
    message: str | None,
) -> tuple[str, str]:
    if action_type is BorrowerActionType.MOVE_FORWARD:
        label = option_label or "your selected option"
        return (
            templates.move_forward_subject(borrower_name, label),
            templates.move_forward_html(
                borrower_name=borrower_name, option_label=label, borrower_email=borrower_email
            ),
        )
    if action_type is BorrowerActionType.ASK_OTHER:
        assert message is not None
        return (
            templates.ask_other_subject(borrower_name),
            templates.ask_other_html(
                borrower_name=borrower_name,
                option_label=option_label,
                message=message,
                borrower_email=borrower_email,
            ),
        )
    return (
        templates.ask_updated_subject(borrower_name),
        templates.ask_updated_html(
            borrower_name=borrower_name, borrower_email=borrower_email, message=message
        ),
    )
