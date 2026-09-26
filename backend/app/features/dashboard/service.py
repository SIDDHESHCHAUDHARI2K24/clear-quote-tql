"""Builds `GET /api/v1/dashboard` (CQ-025 spec.md): seven scoped tile
counts, plus the "Needs your attention", "Going stale" and "Recent
activity" lists.

Every query goes through `core.auth.scope_applications` so an LO only ever
sees their own files and a Manager/Admin sees all files or one LO's (E16).
No money math here (AGENTS.md) -- this reads already-priced `Quote.rate`/
`priced_at` and already-sent `QuotePackageVersion` rows, never recomputes a
number.

The "Pre-approvals sent" tile uses
`applications.listing.service.build_sent_or_later_filter()` -- the same
filter `GET /applications?status=sent_or_later` applies (CQ-027 spec.md
AC3, plan.md Decision #6/E10) -- rather than a locally duplicated status
set, so a Stale application that aged out straight from Priced without
ever being sent (CQ-030 spec.md) is excluded from both.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.auth import scope_applications
from app.core.enums import ApplicationStatus, UserRole
from app.features.applications.listing.service import build_sent_or_later_filter
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.dashboard.schemas import (
    ActivityItem,
    AttentionItem,
    DashboardLoOption,
    DashboardResponse,
    DashboardTiles,
    StaleItem,
)
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion

STALE_AFTER_DAYS = 21
"""spec.md: "the recommended quote or sent version is older than 21 days"."""

_ATTENTION_STATUSES = frozenset(
    {
        ApplicationStatus.NEEDS_ATTENTION,
        ApplicationStatus.INQUIRY,
        ApplicationStatus.OPTION_SELECTED,
    }
)
_AWAITING_REVIEW_STATUSES = frozenset(
    {ApplicationStatus.PRICED, ApplicationStatus.INQUIRY, ApplicationStatus.OPTION_SELECTED}
)
_NOT_ACTIVE_STATUSES = frozenset({ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED})

_ATTENTION_LIMIT = 10
_STALE_LIMIT = 10
_ACTIVITY_LIMIT = 20
_REASON_EXCERPT_LENGTH = 140

_DEFAULT_NEEDS_ATTENTION_REASON = "Needs review"
_DEFAULT_INQUIRY_REASON = "Borrower has a question"
_DEFAULT_OPTION_SELECTED_REASON = "Selected an option"


def _scoped(stmt: Select, user: User, lo_id: uuid.UUID | None) -> Select:
    return scope_applications(stmt, user, lo_id)


async def _count(db: AsyncSession, stmt: Select) -> int:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    return (await db.execute(count_stmt)).scalar_one()


async def _build_tiles(db: AsyncSession, user: User, lo_id: uuid.UUID | None) -> DashboardTiles:
    clients_stmt = _scoped(
        select(func.count(func.distinct(Application.client_id))).select_from(Application),
        user,
        lo_id,
    )
    applications_stmt = _scoped(
        select(Application.id).where(Application.status.notin_(_NOT_ACTIVE_STATUSES)), user, lo_id
    )
    pre_approvals_sent_stmt = _scoped(
        select(Application.id).where(build_sent_or_later_filter()),
        user,
        lo_id,
    )
    with_property_stmt = _scoped(
        select(Application.id)
        .join(Property, Property.application_id == Application.id)
        .where(Property.address_status == PropertyAddressStatus.SPECIFIC_ADDRESS),
        user,
        lo_id,
    )
    awaiting_review_stmt = _scoped(
        select(Application.id).where(Application.status.in_(_AWAITING_REVIEW_STATUSES)), user, lo_id
    )
    needs_attention_stmt = _scoped(
        select(Application.id).where(Application.status == ApplicationStatus.NEEDS_ATTENTION),
        user,
        lo_id,
    )
    stale_quotes_stmt = _scoped(
        select(Application.id).where(Application.status == ApplicationStatus.STALE), user, lo_id
    )

    return DashboardTiles(
        clients=(await db.execute(clients_stmt)).scalar_one(),
        applications=await _count(db, applications_stmt),
        pre_approvals_sent=await _count(db, pre_approvals_sent_stmt),
        with_property=await _count(db, with_property_stmt),
        awaiting_review=await _count(db, awaiting_review_stmt),
        needs_attention=await _count(db, needs_attention_stmt),
        stale_quotes=await _count(db, stale_quotes_stmt),
    )


async def _needs_attention_reasons(
    db: AsyncSession, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Batched (code review: avoids one query per attention-list row): the
    earliest unresolved `Flag.message` per application, for every id in
    `application_ids` in a single `DISTINCT ON` query."""
    if not application_ids:
        return {}
    stmt = (
        select(Flag.application_id, Flag.message)
        .where(Flag.application_id.in_(application_ids), Flag.resolved_at.is_(None))
        .order_by(Flag.application_id, Flag.created_at.asc())
        .ext(distinct_on(Flag.application_id))
    )
    rows = (await db.execute(stmt)).all()
    return {
        application_id: message or _DEFAULT_NEEDS_ATTENTION_REASON
        for application_id, message in rows
    }


async def _latest_sent_versions(
    db: AsyncSession, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, QuotePackageVersion]:
    """Batched: the most-recently-*sent* `QuotePackageVersion` per
    application, for every id in `application_ids` in a single
    `DISTINCT ON` query.

    Orders by `sent_at DESC` (version as a same-`sent_at` tiebreaker), not
    `version` alone -- `application_id` has no unique constraint on
    `quote_packages` (code review, cq-025-fix), so ordering by version
    number alone would pick the wrong package's version if an application
    ever had more than one `QuotePackage` row (today it never does -- one
    package per application, CQ-020's resend path adds a version to the
    *same* package, per `quote_packages`/`quote_package_versions`'
    module docstring -- but this keeps the same "latest sent" definition
    `_build_stale`'s `latest_sent_at` subquery already uses, rather than a
    second, inconsistent one)."""
    if not application_ids:
        return {}
    stmt = (
        select(QuotePackage.application_id, QuotePackageVersion)
        .join(QuotePackage, QuotePackage.id == QuotePackageVersion.package_id)
        .where(QuotePackage.application_id.in_(application_ids))
        .order_by(
            QuotePackage.application_id,
            QuotePackageVersion.sent_at.desc(),
            QuotePackageVersion.version.desc(),
        )
        .ext(distinct_on(QuotePackage.application_id))
    )
    rows = (await db.execute(stmt)).all()
    return dict(rows)


def _excerpt(text: str, *, length: int = _REASON_EXCERPT_LENGTH) -> str:
    stripped = text.strip()
    if len(stripped) <= length:
        return stripped
    return stripped[: length - 1].rstrip() + "…"


def _option_label(version: QuotePackageVersion, quote_id: str | None) -> str | None:
    if quote_id is None or not isinstance(version.snapshot, dict):
        return None
    for option in version.snapshot.get("options", []):
        if isinstance(option, dict) and option.get("quote_id") == quote_id:
            label = option.get("label")
            return label if isinstance(label, str) else None
    return None


def _inquiry_reason(version: QuotePackageVersion | None) -> str:
    action = version.borrower_action if version is not None else None
    if isinstance(action, dict):
        message = action.get("message")
        if isinstance(message, str) and message.strip():
            return _excerpt(message)
    return _DEFAULT_INQUIRY_REASON


def _option_selected_reason(version: QuotePackageVersion | None) -> str:
    action = version.borrower_action if version is not None else None
    if version is not None and isinstance(action, dict):
        label = _option_label(version, action.get("quote_id"))
        if label:
            return label
    return _DEFAULT_OPTION_SELECTED_REASON


async def _build_attention(
    db: AsyncSession, user: User, lo_id: uuid.UUID | None, now: datetime
) -> list[AttentionItem]:
    stmt = (
        _scoped(
            select(
                Application.id, Application.status, Application.updated_at, Client.full_name
            ).join(Client, Client.id == Application.client_id),
            user,
            lo_id,
        )
        .where(Application.status.in_(_ATTENTION_STATUSES))
        .order_by(Application.updated_at.asc())
        .limit(_ATTENTION_LIMIT)
    )
    rows = (await db.execute(stmt)).all()

    needs_attention_ids = [
        application_id
        for application_id, status, _, _ in rows
        if status is ApplicationStatus.NEEDS_ATTENTION
    ]
    sent_version_ids = [
        application_id
        for application_id, status, _, _ in rows
        if status is not ApplicationStatus.NEEDS_ATTENTION
    ]
    needs_attention_reasons = await _needs_attention_reasons(db, needs_attention_ids)
    latest_sent_versions = await _latest_sent_versions(db, sent_version_ids)

    items: list[AttentionItem] = []
    for application_id, status, updated_at, client_name in rows:
        if status is ApplicationStatus.NEEDS_ATTENTION:
            reason = needs_attention_reasons.get(application_id, _DEFAULT_NEEDS_ATTENTION_REASON)
        elif status is ApplicationStatus.INQUIRY:
            reason = _inquiry_reason(latest_sent_versions.get(application_id))
        else:
            reason = _option_selected_reason(latest_sent_versions.get(application_id))
        items.append(
            AttentionItem(
                application_id=application_id,
                client_name=client_name,
                status=status,
                reason=reason,
                age_days=max((now - updated_at).days, 0),
            )
        )
    return items


async def _build_stale(
    db: AsyncSession, user: User, lo_id: uuid.UUID | None, now: datetime
) -> list[StaleItem]:
    latest_sent_at = (
        select(
            QuotePackage.application_id.label("application_id"),
            func.max(QuotePackageVersion.sent_at).label("latest_sent_at"),
        )
        .join(QuotePackageVersion, QuotePackageVersion.package_id == QuotePackage.id)
        .group_by(QuotePackage.application_id)
        .subquery()
    )
    reference_at = func.coalesce(latest_sent_at.c.latest_sent_at, Quote.priced_at)
    cutoff = now - timedelta(days=STALE_AFTER_DAYS)

    stmt = (
        _scoped(
            select(Application.id, Client.full_name, reference_at.label("reference_at"))
            .join(Client, Client.id == Application.client_id)
            .outerjoin(latest_sent_at, latest_sent_at.c.application_id == Application.id)
            .outerjoin(Quote, Quote.id == Application.recommended_quote_id),
            user,
            lo_id,
        )
        .where(Application.status.notin_(_NOT_ACTIVE_STATUSES))
        .where(reference_at.isnot(None))
        .where(reference_at < cutoff)
        .order_by(reference_at.asc())
        .limit(_STALE_LIMIT)
    )
    rows = (await db.execute(stmt)).all()
    return [
        StaleItem(
            application_id=application_id,
            client_name=client_name,
            days_old=(now - ref_at).days,
        )
        for application_id, client_name, ref_at in rows
    ]


_SYSTEM_ACTOR = "system"


async def _actor_labels(db: AsyncSession, actors: set[str]) -> dict[str, str]:
    """`ActivityEvent.actor` stores a `User.id` (as a string) or the literal
    `"system"` (timeline/models.py). Resolves every user-id actor to that
    user's `full_name` in one batched query, so the feed reads "Jordan Lee"
    rather than a raw UUID; a deleted/unresolvable user id falls back to
    itself."""
    user_ids: list[uuid.UUID] = []
    for actor in actors:
        if actor == _SYSTEM_ACTOR:
            continue
        try:
            user_ids.append(uuid.UUID(actor))
        except ValueError:
            continue
    if not user_ids:
        return {}
    stmt = select(User.id, User.full_name).where(User.id.in_(user_ids))
    rows = (await db.execute(stmt)).all()
    return {str(user_id): full_name for user_id, full_name in rows}


async def _build_activity(
    db: AsyncSession, user: User, lo_id: uuid.UUID | None
) -> list[ActivityItem]:
    stmt = (
        _scoped(
            select(
                ActivityEvent.id,
                ActivityEvent.actor,
                ActivityEvent.type,
                ActivityEvent.application_id,
                ActivityEvent.at,
                Client.full_name,
            )
            .join(Application, Application.id == ActivityEvent.application_id)
            .join(Client, Client.id == Application.client_id),
            user,
            lo_id,
        )
        .order_by(ActivityEvent.at.desc())
        .limit(_ACTIVITY_LIMIT)
    )
    rows = (await db.execute(stmt)).all()
    labels = await _actor_labels(db, {actor for _, actor, *_ in rows})
    return [
        ActivityItem(
            id=event_id,
            actor="System" if actor == _SYSTEM_ACTOR else labels.get(actor, actor),
            type=event_type,
            application_id=application_id,
            at=at,
            client_name=client_name,
        )
        for event_id, actor, event_type, application_id, at, client_name in rows
    ]


async def _build_los(db: AsyncSession, user: User) -> list[DashboardLoOption] | None:
    if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        return None
    stmt = (
        select(User.id, User.full_name)
        .where(User.role == UserRole.LO)
        .order_by(User.full_name, User.id)
    )
    rows = (await db.execute(stmt)).all()
    return [DashboardLoOption(id=lo_id, full_name=full_name) for lo_id, full_name in rows]


async def build_dashboard(
    db: AsyncSession, user: User, lo_id: uuid.UUID | None
) -> DashboardResponse:
    now = clock.now()
    tiles = await _build_tiles(db, user, lo_id)
    attention = await _build_attention(db, user, lo_id, now)
    stale = await _build_stale(db, user, lo_id, now)
    activity = await _build_activity(db, user, lo_id)
    los = await _build_los(db, user)

    return DashboardResponse(
        tiles=tiles, attention=attention, stale=stale, activity=activity, los=los
    )
