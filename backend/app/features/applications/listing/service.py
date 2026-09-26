"""`GET /applications` query building (spec.md CQ-027 "Backend").

`build_sent_or_later_filter()` is the one thing outside this feature is
meant to import: CQ-025's dashboard "Pre-approvals sent" tile must return
the same count as `status=sent_or_later` here (spec.md AC3, plan.md's
Decision #6/E10) -- rather than each item writing its own copy of "Sent,
Viewed, Inquiry, OptionSelected, or Stale after a send", the dashboard
imports this function and applies it to its own scoped `Application`
query.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import scope_applications
from app.core.enums import ApplicationStatus, Strategy, UserRole
from app.core.errors import ValidationAppError
from app.core.pagination import Page, paginate
from app.core.sql import LIKE_ESCAPE_CHAR, escape_like
from app.features.applications.listing.schemas import ApplicationRow, LoOption, StrategyLabel
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.verification.models import Flag
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion

# spec.md `status=sent_or_later`: "Sent, Viewed, Inquiry, OptionSelected".
# `Stale` only counts when the application was actually sent first (see
# `build_sent_or_later_filter`) -- per CQ-030 spec.md an application can
# also reach Stale straight from Priced (its quote just aged out) without
# ever being sent, and that case must NOT count as "sent or later".
_SENT_OR_LATER_BASE_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.SENT,
        ApplicationStatus.VIEWED,
        ApplicationStatus.INQUIRY,
        ApplicationStatus.OPTION_SELECTED,
    }
)

SENT_OR_LATER_ALIAS = "sent_or_later"


def _pascal_label(status: ApplicationStatus) -> str:
    """`needs_attention` -> `NeedsAttention` -- the spec's own status labels
    (spec.md's parameter table; CQ-025's tile links, e.g.
    `?status=Priced,Inquiry,OptionSelected`)."""
    return "".join(word.capitalize() for word in status.value.split("_"))


_STATUS_LABEL_TO_ENUM: dict[str, ApplicationStatus] = {}
for _status in ApplicationStatus:
    _STATUS_LABEL_TO_ENUM[_pascal_label(_status)] = _status
    _STATUS_LABEL_TO_ENUM[_status.value] = _status


def build_sent_or_later_filter() -> ColumnElement[bool]:
    """A boolean SQL expression over `Application` for spec.md's
    `sent_or_later` alias -- import this directly rather than
    re-deriving it (plan.md Decision #6)."""
    sent_exists = (
        select(QuotePackageVersion.id)
        .join(QuotePackage, QuotePackageVersion.package_id == QuotePackage.id)
        .where(QuotePackage.application_id == Application.id)
        .correlate(Application)
        .exists()
    )
    return or_(
        Application.status.in_(_SENT_OR_LATER_BASE_STATUSES),
        and_(Application.status == ApplicationStatus.STALE, sent_exists),
    )


def _status_filter(raw: str) -> ColumnElement[bool]:
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        raise ValidationAppError("status must not be empty")
    clauses: list[ColumnElement[bool]] = []
    for token in tokens:
        if token == SENT_OR_LATER_ALIAS:
            clauses.append(build_sent_or_later_filter())
            continue
        enum_value = _STATUS_LABEL_TO_ENUM.get(token)
        if enum_value is None:
            raise ValidationAppError(f"Unknown status: {token}")
        clauses.append(Application.status == enum_value)
    return or_(*clauses)


_STRATEGY_TOKENS = {"primary", "ltr", "str"}


def _strategy_filter(raw: str) -> ColumnElement[bool]:
    tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
    if not tokens:
        raise ValidationAppError("strategy must not be empty")
    clauses: list[ColumnElement[bool]] = []
    for token in tokens:
        if token not in _STRATEGY_TOKENS:
            raise ValidationAppError(f"Unknown strategy: {token}")
        if token == "primary":
            clauses.append(Application.strategy.is_(None))
        elif token == "ltr":
            clauses.append(Application.strategy == Strategy.LTR)
        else:
            clauses.append(Application.strategy == Strategy.STR)
    return or_(*clauses)


def _strategy_label(strategy: Strategy | None) -> StrategyLabel:
    """Mirrors `_strategy_filter`'s `primary` rule: `applications.strategy`
    is `NULL` exactly when the loan is Primary (`core/enums.py` `Strategy`
    docstring)."""
    if strategy == Strategy.LTR:
        return "ltr"
    if strategy == Strategy.STR:
        return "str"
    return "primary"


def _property_label(
    address_status: PropertyAddressStatus | None,
    street_address: str | None,
    city: str | None,
    state: str | None,
    buy_box_metros: list[str] | None,
) -> str | None:
    """spec.md "Row": the address, or `"TBD · {metros}"`, or `None` when
    the application has no `properties` row at all (plan.md Decision #8;
    the ~200 bare background-seed applications never get one)."""
    if address_status is None:
        return None
    if address_status == PropertyAddressStatus.SPECIFIC_ADDRESS:
        parts = [p for p in (street_address, city, state) if p]
        return ", ".join(parts) if parts else None
    metros = buy_box_metros or []
    return f"TBD · {', '.join(metros)}" if metros else "TBD"


_SORT_COLUMNS: dict[str, Any] = {
    "amount": Application.requested_price,
    "client": Client.full_name,
    "status": Application.status,
    "updated_at": Application.updated_at,
}


def _order_by(sort: str) -> list[ColumnElement[Any]]:
    token = sort.strip()
    descending = token.startswith("-")
    key = token[1:] if descending else token
    column = _SORT_COLUMNS.get(key)
    if column is None:
        raise ValidationAppError(f"Unknown sort: {sort}")
    primary = column.desc() if descending else column.asc()
    # Stable tie-breaker (core/pagination.py's contract: `stmt` must carry
    # its own stable `ORDER BY`).
    return [primary, Application.id.asc()]


def _base_query() -> Select[*tuple[Any, ...]]:
    flag_count = (
        select(func.count(Flag.id))
        .where(Flag.application_id == Application.id, Flag.resolved_at.is_(None))
        .correlate(Application)
        .scalar_subquery()
    )
    return (
        select(
            Application.id,
            Client.full_name.label("client_name"),
            Application.strategy,
            Application.requested_price,
            Application.status,
            flag_count.label("flag_count"),
            Application.lo_id,
            User.full_name.label("lo_name"),
            Application.updated_at,
            Property.address_status,
            Property.street_address,
            Property.city,
            Property.state,
            Property.buy_box_metros,
        )
        .select_from(Application)
        .join(Client, Client.id == Application.client_id)
        .join(User, User.id == Application.lo_id)
        .outerjoin(Property, Property.application_id == Application.id)
    )


def _row_to_schema(row: Any) -> ApplicationRow:
    return ApplicationRow(
        id=row.id,
        client_name=row.client_name,
        property_label=_property_label(
            row.address_status,
            row.street_address,
            row.city,
            row.state,
            row.buy_box_metros,
        ),
        strategy=_strategy_label(row.strategy),
        purchase_price=row.requested_price,
        status=row.status,
        flag_count=row.flag_count,
        lo_id=row.lo_id,
        lo_name=row.lo_name,
        updated_at=row.updated_at,
    )


async def list_applications(
    db: AsyncSession,
    user: User,
    *,
    q: str | None = None,
    lo_id: uuid.UUID | None = None,
    status: str | None = None,
    strategy: str | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    state: str | None = None,
    has_property: bool | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    sort: str = "-updated_at",
    page: int | None = 1,
    page_size: int | None = None,
) -> Page[ApplicationRow]:
    """Builds and runs `GET /applications` (spec.md). `user`/`lo_id` go
    through `core.auth.scope_applications` (an LO's own `lo_id` is always
    ignored, Decision -- spec.md's own wording); every other parameter is
    from the spec's table."""
    stmt = scope_applications(_base_query(), user, lo_id)

    if q:
        # `%`/`_` in `q` are escaped so a literal search term can't act as a
        # SQL LIKE wildcard (review round 1, CQ-026 -- same fix as
        # `clients/service.py`'s search and the outbox's).
        needle = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                Client.full_name.ilike(needle, escape=LIKE_ESCAPE_CHAR),
                Client.email.ilike(needle, escape=LIKE_ESCAPE_CHAR),
            )
        )
    if status:
        stmt = stmt.where(_status_filter(status))
    if strategy:
        stmt = stmt.where(_strategy_filter(strategy))
    if amount_min is not None:
        stmt = stmt.where(Application.requested_price >= amount_min)
    if amount_max is not None:
        stmt = stmt.where(Application.requested_price <= amount_max)
    if state:
        state_code = state.strip().upper()
        stmt = stmt.where(
            or_(
                and_(
                    Property.address_status == PropertyAddressStatus.SPECIFIC_ADDRESS,
                    Property.state == state_code,
                ),
                and_(
                    Property.address_status == PropertyAddressStatus.TBD,
                    func.array_position(Property.buy_box_states, state_code).is_not(None),
                ),
            )
        )
    if has_property is True:
        stmt = stmt.where(Property.address_status == PropertyAddressStatus.SPECIFIC_ADDRESS)
    elif has_property is False:
        stmt = stmt.where(
            or_(
                Property.address_status.is_(None),
                Property.address_status == PropertyAddressStatus.TBD,
            )
        )
    if created_from is not None:
        stmt = stmt.where(
            Application.created_at >= datetime.combine(created_from, time.min, tzinfo=UTC)
        )
    if created_to is not None:
        stmt = stmt.where(
            Application.created_at
            < datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=UTC)
        )

    stmt = stmt.order_by(*_order_by(sort))

    result = await paginate(db, stmt, page, page_size)
    return Page[ApplicationRow](
        items=[_row_to_schema(row) for row in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


async def list_lo_options(db: AsyncSession) -> list[LoOption]:
    """Every `role=lo` user, alphabetical by name -- backs the frontend's
    LO `Select` (Manager/Admin only, spec.md "Frontend")."""
    stmt = select(User.id, User.full_name).where(User.role == UserRole.LO).order_by(User.full_name)
    rows = (await db.execute(stmt)).all()
    return [LoOption(id=row.id, full_name=row.full_name) for row in rows]
