"""FastAPI dependencies for staff auth: who's signed in, role gates, and
LO/Manager application scoping (plan.md Decision #11).

No endpoint outside `features/auth/staff` should read the `cq_staff_session`
cookie directly — everything else depends on `get_current_staff` (or the
`CurrentStaff` alias) instead.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Cookie, Depends
from redis.asyncio import Redis
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.enums import UserRole
from app.core.errors import AuthenticationError, ForbiddenError
from app.core.valkey import get_valkey
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.auth.sessions.service import COOKIE_NAMES, get_session_subject

_NOT_SIGNED_IN = "Not signed in"


async def get_current_staff(
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAMES["staff"]),
) -> User:
    """Resolves the signed-in staff `User` from the `cq_staff_session`
    cookie. Raises `AuthenticationError` for a missing cookie, an
    expired/unknown session, or a session whose user has been deleted.
    """
    if session_token is None:
        raise AuthenticationError(_NOT_SIGNED_IN)

    subject_id = await get_session_subject(valkey, principal="staff", token=session_token)
    if subject_id is None:
        raise AuthenticationError(_NOT_SIGNED_IN)

    user = await db.get(User, uuid.UUID(subject_id))
    if user is None:
        raise AuthenticationError(_NOT_SIGNED_IN)
    return user


CurrentStaff = Annotated[User, Depends(get_current_staff)]


def require_roles(*roles: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
    """A dependency that 403s (`ForbiddenError`) unless the signed-in
    staff user's role is one of `roles`; otherwise returns that user."""

    async def _dependency(user: CurrentStaff) -> User:
        if user.role not in roles:
            raise ForbiddenError("You do not have access to this resource")
        return user

    return _dependency


def scope_applications(stmt: Select, user: User, lo_id: uuid.UUID | None = None) -> Select:
    """Restricts `stmt` (a `select(Application...)` statement) to what
    `user` may see: an LO only ever sees their own applications (`lo_id`
    is ignored for them); a Manager/Admin sees all applications, or just
    one LO's when `lo_id` is given.
    """
    if user.role == UserRole.LO:
        return stmt.where(Application.lo_id == user.id)
    if lo_id is not None:
        return stmt.where(Application.lo_id == lo_id)
    return stmt
