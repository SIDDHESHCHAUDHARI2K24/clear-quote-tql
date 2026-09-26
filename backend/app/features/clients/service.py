"""`GET /clients` and `GET /clients/{id}` (spec.md CQ-026 "Backend")."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.auth import scope_applications
from app.core.config import get_settings
from app.core.enums import ApplicationStatus, Strategy, UserRole
from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import Page, paginate
from app.core.sql import LIKE_ESCAPE_CHAR, escape_like
from app.features.applications.listing.schemas import ApplicationRow, StrategyLabel
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.timeline.service import list_activity_for_applications
from app.features.applications.verification.models import Flag
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.clients.schemas import (
    ClientDetail,
    ClientRow,
    ClientSentVersion,
    SentVersionStatus,
)
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion

_TERMINAL_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED}
)
"""plan.md Decision 1/3: "active" means not one of these two -- mirrors the
enum's own docstring ("the terminal `withdrawn`/`closed` states")."""


def _client_has_lo_application(lo_id_param: Any) -> ColumnElement[bool]:
    return (
        select(Application.id)
        .where(Application.client_id == Client.id, Application.lo_id == lo_id_param)
        .correlate(Client)
        .exists()
    )


def scope_clients(stmt: Select, user: User, lo_id: uuid.UUID | None = None) -> Select:
    """plan.md Decision 1: scoped by `Application.lo_id` (not
    `Client.assigned_lo_id`) -- "An LO never sees clients whose applications
    all belong to other LOs" (spec.md AC3). A client with zero applications
    is therefore invisible to a scoped LO but still visible to an
    unscoped Manager/Admin. An LO's own `lo_id` query param is ignored,
    same convention as `applications.listing.service.list_applications`.
    """
    if user.role == UserRole.LO:
        return stmt.where(_client_has_lo_application(user.id))
    if lo_id is not None:
        return stmt.where(_client_has_lo_application(lo_id))
    return stmt


_SORT_KEYS = frozenset({"name", "created_at", "last_activity"})
"""plan.md Decision 4: exactly the three spec.md tokens are accepted."""


def _order_by(sort: str, last_activity_expr: Any) -> list[ColumnElement[Any]]:
    token = sort.strip()
    descending = token.startswith("-")
    key = token[1:] if descending else token
    if key not in _SORT_KEYS:
        raise ValidationAppError(f"Unknown sort: {sort}")
    column = {
        "name": Client.full_name,
        "created_at": Client.created_at,
        "last_activity": last_activity_expr,
    }[key]
    # `nulls_last()` on every direction: a client with no `last_activity` yet
    # (never had an activity event) sorts to the end either way, rather than
    # Postgres's default (NULLS FIRST for DESC) putting it confusingly first.
    primary = column.desc().nulls_last() if descending else column.asc().nulls_last()
    # Stable tie-breaker (core/pagination.py's contract).
    return [primary, Client.id.asc()]


def _application_scope_clauses(lo_scope: uuid.UUID | None) -> list[ColumnElement[bool]]:
    """The `Application` rows every list-level aggregate below is computed
    over: a client's own applications, additionally restricted to
    `lo_scope`'s when given.

    Review round 1 (CQ-026): an LO's `application_count`/`active_status`/
    `last_activity` were computed over the client's *entire* application
    set, including other LOs'. `application_count` in particular could
    reveal that another LO has applications with a shared client -- so for
    a requesting LO (`lo_scope=user.id`), every aggregate is now scoped to
    just their own applications, matching what `get_client_detail` shows
    them. A Manager/Admin's aggregates stay unscoped (`lo_scope=None`)
    even when filtering the list by `lo_id`: that filter narrows which
    clients appear, not what a Manager -- who can already see everything
    -- is told about them (plan.md Decision, review round 1)."""
    clauses: list[ColumnElement[bool]] = [Application.client_id == Client.id]
    if lo_scope is not None:
        clauses.append(Application.lo_id == lo_scope)
    return clauses


def _base_query(lo_scope: uuid.UUID | None = None) -> tuple[Select[*tuple[Any, ...]], Any]:
    application_count = (
        select(func.count(Application.id))
        .where(*_application_scope_clauses(lo_scope))
        .correlate(Client)
        .scalar_subquery()
    )
    active_status = (
        select(Application.status)
        .where(
            *_application_scope_clauses(lo_scope),
            Application.status.notin_(_TERMINAL_STATUSES),
        )
        .order_by(Application.updated_at.desc())
        .limit(1)
        .correlate(Client)
        .scalar_subquery()
    )
    last_activity = (
        select(func.max(ActivityEvent.at))
        .select_from(ActivityEvent)
        .join(Application, Application.id == ActivityEvent.application_id)
        .where(*_application_scope_clauses(lo_scope))
        .correlate(Client)
        .scalar_subquery()
    )
    stmt = (
        select(
            Client.id,
            Client.full_name.label("name"),
            Client.email,
            Client.phone,
            Client.assigned_lo_id.label("lo_id"),
            User.full_name.label("lo_name"),
            application_count.label("application_count"),
            active_status.label("active_status"),
            last_activity.label("last_activity"),
            Client.created_at,
        )
        .select_from(Client)
        .join(User, User.id == Client.assigned_lo_id)
    )
    return stmt, last_activity


def _row_to_schema(row: Any) -> ClientRow:
    return ClientRow(
        id=row.id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        lo_id=row.lo_id,
        lo_name=row.lo_name,
        application_count=row.application_count,
        active_status=row.active_status,
        last_activity=row.last_activity,
    )


async def list_clients(
    db: AsyncSession,
    user: User,
    *,
    q: str | None = None,
    lo_id: uuid.UUID | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    has_active: bool | None = None,
    sort: str = "-last_activity",
    page: int | None = 1,
    page_size: int | None = None,
) -> Page[ClientRow]:
    lo_scope = user.id if user.role == UserRole.LO else None
    stmt, last_activity_expr = _base_query(lo_scope)
    stmt = scope_clients(stmt, user, lo_id)

    if q:
        # `%`/`_` escaped so a literal search term can't act as a SQL LIKE
        # wildcard (review round 1, CQ-026).
        needle = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                Client.full_name.ilike(needle, escape=LIKE_ESCAPE_CHAR),
                Client.email.ilike(needle, escape=LIKE_ESCAPE_CHAR),
            )
        )
    if created_from is not None:
        stmt = stmt.where(Client.created_at >= datetime.combine(created_from, time.min, tzinfo=UTC))
    if created_to is not None:
        stmt = stmt.where(
            Client.created_at
            < datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=UTC)
        )
    if has_active is True:
        stmt = stmt.where(_client_active_exists(lo_scope))
    elif has_active is False:
        stmt = stmt.where(~_client_active_exists(lo_scope))

    stmt = stmt.order_by(*_order_by(sort, last_activity_expr))

    result = await paginate(db, stmt, page, page_size)
    return Page[ClientRow](
        items=[_row_to_schema(row) for row in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


def _client_active_exists(lo_scope: uuid.UUID | None = None) -> ColumnElement[bool]:
    """Review round 2: scoped by `lo_scope` the same way
    `_application_scope_clauses` scopes the other list-level aggregates --
    otherwise an LO's `has_active` filter answers "does *anyone's*
    application count as active" instead of their own, leaking whether
    another LO has active work on a shared client (both directions:
    `true` would surface a client whose only active application is the
    other LO's, and `false` would hide a client whose *own* application
    isn't active just because the other LO's is)."""
    return (
        select(Application.id)
        .where(*_application_scope_clauses(lo_scope), Application.status.notin_(_TERMINAL_STATUSES))
        .correlate(Client)
        .exists()
    )


# --- Detail ------------------------------------------------------------


def _strategy_label(strategy: Strategy | None) -> StrategyLabel:
    """Duplicated from `applications.listing.service._strategy_label`
    (plan.md Decision 6: small, feature-local copy rather than importing
    another feature's private symbol -- same precedent as
    `portal/reports/versions.py::_strategy_type`)."""
    if strategy == Strategy.LTR:
        return "ltr"
    if strategy == Strategy.STR:
        return "str"
    return "primary"


def _property_label(prop: Property | None) -> str | None:
    """Duplicated from `applications.listing.service._property_label`
    (plan.md Decision 6)."""
    if prop is None:
        return None
    if prop.address_status == PropertyAddressStatus.SPECIFIC_ADDRESS:
        parts = [p for p in (prop.street_address, prop.city, prop.state) if p]
        return ", ".join(parts) if parts else None
    metros = prop.buy_box_metros or []
    return f"TBD · {', '.join(metros)}" if metros else "TBD"


async def _application_rows_for_client(
    db: AsyncSession, client_id: uuid.UUID, user: User
) -> list[Application]:
    """`user`-scoped applications for this client (review round 1, CQ-026 --
    critical: this used to return every application regardless of role,
    so an LO's client-detail page leaked other LOs' applications, sent
    versions and activity for a client they shared. `scope_applications`
    is the same helper every other application-scoped route uses --
    `core/auth.py`'s "an LO only ever sees their own applications" -- so an
    LO gets just their own rows here and a Manager/Admin still gets every
    application, matching CQ-014's role scoping."""
    stmt = scope_applications(
        select(Application).where(Application.client_id == client_id), user
    ).order_by(Application.updated_at.desc(), Application.id.asc())
    return list((await db.execute(stmt)).scalars().all())


async def _application_rows(
    db: AsyncSession, client: Client, applications: list[Application]
) -> list[ApplicationRow]:
    """Each application keeps its own `lo_id`/`lo_name` (not necessarily
    `client.assigned_lo_id`'s -- a client can have applications assigned to
    different LOs over time, and `ApplicationRow.lo_id` must reflect the
    application's own, same as CQ-027's list)."""
    if not applications:
        return []
    app_ids = [a.id for a in applications]
    lo_ids = {a.lo_id for a in applications}

    flag_counts = dict(
        (
            await db.execute(
                select(Flag.application_id, func.count(Flag.id))
                .where(Flag.application_id.in_(app_ids), Flag.resolved_at.is_(None))
                .group_by(Flag.application_id)
            )
        ).all()
    )
    properties = {
        p.application_id: p
        for p in (await db.execute(select(Property).where(Property.application_id.in_(app_ids))))
        .scalars()
        .all()
    }
    lo_names = dict(
        (await db.execute(select(User.id, User.full_name).where(User.id.in_(lo_ids)))).all()
    )

    rows: list[ApplicationRow] = []
    for application in applications:
        rows.append(
            ApplicationRow(
                id=application.id,
                client_name=client.full_name,
                property_label=_property_label(properties.get(application.id)),
                strategy=_strategy_label(application.strategy),
                purchase_price=application.requested_price,
                status=application.status,
                flag_count=flag_counts.get(application.id, 0),
                lo_id=application.lo_id,
                lo_name=lo_names.get(application.lo_id, "Unknown"),
                updated_at=application.updated_at,
            )
        )
    return rows


def _version_status(version: QuotePackageVersion, now: datetime) -> SentVersionStatus:
    """plan.md Decision 9."""
    if version.superseded:
        return "superseded"
    if version.expired_at is not None or now >= version.expires_at:
        return "expired"
    if isinstance(version.borrower_action, dict):
        action_type = version.borrower_action.get("type")
        if action_type in (
            "option_selected",
            "move_forward",
            "ask_other",
            "ask_updated",
            "inquiry",
        ):
            return action_type  # type: ignore[return-value]
    if version.viewed_at is not None:
        return "viewed"
    return "sent"


def _recommended_option_label(snapshot: Any) -> str | None:
    """plan.md Decision 10: `options[]` of the frozen `ReportViewModel`
    (`quotes/report/schemas.py::ReportOption`)."""
    if not isinstance(snapshot, dict):
        return None
    options = snapshot.get("options")
    if not isinstance(options, list):
        return None
    for option in options:
        if isinstance(option, dict) and option.get("recommended"):
            label = option.get("label")
            return label if isinstance(label, str) else None
    return None


async def _sent_versions_for_client(
    db: AsyncSession, application_ids: list[uuid.UUID]
) -> list[ClientSentVersion]:
    if not application_ids:
        return []
    stmt = (
        select(QuotePackageVersion, QuotePackage.application_id)
        .join(QuotePackage, QuotePackageVersion.package_id == QuotePackage.id)
        .where(QuotePackage.application_id.in_(application_ids))
        .order_by(QuotePackageVersion.sent_at.desc())
    )
    now = clock.now()
    # code review finding: the LO console and borrower portal are separate
    # Next.js apps on different origins, so a bare relative `/report/...`
    # path (resolved against the LO console's own origin from
    # `SentVersionsTable.tsx`'s `<a href=...>`) 404s -- build the full
    # borrower-portal URL instead, same as `applications/sections/credit.py`
    # already does for its consent-request link.
    portal_base_url = get_settings().portal_base_url.rstrip("/")
    rows: list[ClientSentVersion] = []
    for version, application_id in (await db.execute(stmt)).all():
        rows.append(
            ClientSentVersion(
                id=version.id,
                application_id=application_id,
                version=version.version,
                sent_at=version.sent_at,
                recommended_option_label=_recommended_option_label(version.snapshot),
                status=_version_status(version, now),
                report_link=f"{portal_base_url}/report/{version.report_token}",
            )
        )
    return rows


async def get_client_detail(db: AsyncSession, user: User, client_id: uuid.UUID) -> ClientDetail:
    client = await db.get(Client, client_id)
    if client is None:
        raise NotFoundError(f"Client not found: {client_id}")

    # `applications` is already `user`-scoped (see
    # `_application_rows_for_client`), so the applications, sent versions
    # and merged activity below are too. An LO with zero in-scope
    # applications for this client gets 404, same as before (review round
    # 1: simplified -- no separate "is one of the client's applications
    # mine" existence check needed, `scope_applications` already answers
    # it). A Manager/Admin still sees every application regardless of
    # count, including zero (list-level "orphan" clients stay visible to
    # them, matching `list_clients`).
    applications = await _application_rows_for_client(db, client_id, user)
    if not applications and user.role == UserRole.LO:
        raise NotFoundError(f"Client not found: {client_id}")

    lo = await db.get(User, client.assigned_lo_id)
    lo_name = lo.full_name if lo is not None else "Unknown"

    application_rows = await _application_rows(db, client, applications)
    sent_versions = await _sent_versions_for_client(db, [a.id for a in applications])
    # Batched (review round 1, minor): one query for the events across
    # every in-scope application plus one staff-name lookup, instead of
    # `list_activity` once per application (each of which re-fetched the
    # client row too).
    activity = await list_activity_for_applications(db, client, applications, limit=50)

    return ClientDetail(
        id=client.id,
        name=client.full_name,
        email=client.email,
        phone=client.phone,
        lo_id=client.assigned_lo_id,
        lo_name=lo_name,
        created_at=client.created_at,
        applications=application_rows,
        sent_versions=sent_versions,
        activity=activity,
    )
