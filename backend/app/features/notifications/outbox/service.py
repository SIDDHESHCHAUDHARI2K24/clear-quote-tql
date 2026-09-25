"""`GET /outbox`, `GET /outbox/{id}`, `GET /outbox/{id}/attachments/{key}`
(spec.md "Outbox").

Scoping (plan.md decision 2, "log the difference"): the spec's AC3 says a
cross-scope LO gets "403"; this follows the codebase's binding rule
instead (plan.md E16 / Decision #11) and 404s, matching every other
`application_id`-scoped resource so an LO can't distinguish "not yours"
from "doesn't exist". An email with no `application_id` (a support-inbox
style send) is visible only to Manager/Admin (spec.md), which this module
enforces the same way: an LO gets 404 for those rows too, both in the list
and the detail/attachment routes.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.errors import NotFoundError
from app.core.pagination import Page, paginate
from app.core.sql import LIKE_ESCAPE_CHAR, escape_like
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail
from app.features.notifications.outbox.schemas import (
    AttachmentOut,
    EmailType,
    OutboxEmailDetail,
    OutboxEmailRow,
)

# Single source of truth for `infer_email_type` (Python classification) and
# `_type_sql_condition` (the `type=` filter's SQL) -- plan.md decision 1.
# Extend this as CQ-020/24/34 land real sends; unmatched subjects fall back
# to "other" until then (logged as a follow-up, not a gap: no AC depends on
# those senders' subjects today).
_TYPE_SUBJECT_RULES: dict[str, tuple[str, ...]] = {
    "otp": ("sign-in code", "already have a Clear Quote account"),
    "borrower_action": (
        "would like to move forward with",
        "has a question about their options",
        "asked for updated numbers",
    ),
    "quote_sent": ("pre-approval is ready",),
}
KNOWN_EMAIL_TYPES = (*_TYPE_SUBJECT_RULES.keys(), "other")

# Columns `list_outbox` actually needs (code review finding: selecting the
# whole `OutboxEmail` entity, including `html`/`attachment_keys`, pulled
# every row's full email body into memory just to discard it on every list
# page).
_LIST_COLUMNS = (
    OutboxEmail.id,
    OutboxEmail.to_email,
    OutboxEmail.subject,
    OutboxEmail.status,
    OutboxEmail.application_id,
    OutboxEmail.created_at,
    OutboxEmail.updated_at,
    Client.full_name.label("client_name"),
)

# `escape_like`/`LIKE_ESCAPE_CHAR` moved to `core.sql` (review round 1,
# CQ-026): shared with `clients/service.py` and
# `applications/listing/service.py` instead of each defining its own copy.


def infer_email_type(subject: str) -> str:
    lowered = subject.lower()
    for type_name, substrings in _TYPE_SUBJECT_RULES.items():
        if any(substring.lower() in lowered for substring in substrings):
            return type_name
    return "other"


def _type_sql_condition(type_name: EmailType) -> Any:
    if type_name in _TYPE_SUBJECT_RULES:
        substrings = _TYPE_SUBJECT_RULES[type_name]
        return or_(*[OutboxEmail.subject.ilike(f"%{s}%") for s in substrings])
    # "other": none of the known substrings match.
    all_substrings = [s for substrings in _TYPE_SUBJECT_RULES.values() for s in substrings]
    if not all_substrings:
        return true()  # pragma: no cover -- defensive, rules are never empty today
    return ~or_(*[OutboxEmail.subject.ilike(f"%{s}%") for s in all_substrings])


def _scope_outbox(stmt: Select, user: User) -> Select:
    """Restricts `stmt` (already outer-joined to `Application`) to what
    `user` may see: an LO only sees rows on their own applications; a
    Manager/Admin sees every row, including application-less ones."""
    if user.role == UserRole.LO:
        return stmt.where(OutboxEmail.application_id.is_not(None), Application.lo_id == user.id)
    return stmt


def _to_row(email: OutboxEmail, client_name: str | None) -> OutboxEmailRow:
    return OutboxEmailRow(
        id=email.id,
        to_email=email.to_email,
        subject=email.subject,
        type=infer_email_type(email.subject),
        status=email.status,
        application_id=email.application_id,
        client_name=client_name,
        sent_at=email.updated_at if email.status == EmailStatus.SENT else None,
        created_at=email.created_at,
    )


def _row_to_out(row: Any) -> OutboxEmailRow:
    """Same mapping as `_to_row`, from a `_LIST_COLUMNS` `Row` instead of a
    full `OutboxEmail` entity."""
    return OutboxEmailRow(
        id=row.id,
        to_email=row.to_email,
        subject=row.subject,
        type=infer_email_type(row.subject),
        status=row.status,
        application_id=row.application_id,
        client_name=row.client_name,
        sent_at=row.updated_at if row.status == EmailStatus.SENT else None,
        created_at=row.created_at,
    )


async def list_outbox(
    db: AsyncSession,
    user: User,
    *,
    q: str | None,
    type: EmailType | None,  # noqa: A002
    application_id: uuid.UUID | None,
    page: int | None,
    page_size: int | None,
) -> Page[OutboxEmailRow]:
    stmt = (
        select(*_LIST_COLUMNS)
        .select_from(OutboxEmail)
        .outerjoin(Application, OutboxEmail.application_id == Application.id)
        .outerjoin(Client, Application.client_id == Client.id)
    )
    stmt = _scope_outbox(stmt, user)

    if q:
        pattern = f"%{escape_like(q)}%"
        stmt = stmt.where(
            or_(
                OutboxEmail.to_email.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                OutboxEmail.subject.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
            )
        )
    if type:
        stmt = stmt.where(_type_sql_condition(type))
    if application_id is not None:
        stmt = stmt.where(OutboxEmail.application_id == application_id)

    stmt = stmt.order_by(OutboxEmail.created_at.desc(), OutboxEmail.id.desc())

    result = await paginate(db, stmt, page, page_size)
    items = [_row_to_out(row) for row in result.items]
    return Page[OutboxEmailRow](
        items=items, total=result.total, page=result.page, page_size=result.page_size
    )


async def get_scoped_outbox_email(db: AsyncSession, user: User, email_id: uuid.UUID) -> OutboxEmail:
    """Resolves `email_id` only within `user`'s scope, else 404 (see module
    docstring)."""
    email = await db.get(OutboxEmail, email_id)
    if email is None:
        raise NotFoundError(f"Outbox email not found: {email_id}")

    if email.application_id is None:
        if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
            raise NotFoundError(f"Outbox email not found: {email_id}")
        return email

    if user.role == UserRole.LO:
        application = await db.get(Application, email.application_id)
        if application is None or application.lo_id != user.id:
            raise NotFoundError(f"Outbox email not found: {email_id}")
    return email


async def get_outbox_email_detail(
    db: AsyncSession, user: User, email_id: uuid.UUID
) -> OutboxEmailDetail:
    email = await get_scoped_outbox_email(db, user, email_id)
    client_name: str | None = None
    if email.application_id is not None:
        application = await db.get(Application, email.application_id)
        if application is not None:
            client = await db.get(Client, application.client_id)
            client_name = client.full_name if client is not None else None

    row = _to_row(email, client_name)
    attachments = [
        AttachmentOut(key=key, filename=key.rsplit("/", 1)[-1]) for key in email.attachment_keys
    ]
    return OutboxEmailDetail(**row.model_dump(), html=email.html, attachments=attachments)


async def get_attachment_key(db: AsyncSession, user: User, email_id: uuid.UUID, key: str) -> str:
    """Resolves `key` only if it's a real attachment of an email `user` may
    see, so the storage stream never serves an arbitrary object key."""
    email = await get_scoped_outbox_email(db, user, email_id)
    if key not in email.attachment_keys:
        raise NotFoundError(f"Attachment not found: {key}")
    return key
