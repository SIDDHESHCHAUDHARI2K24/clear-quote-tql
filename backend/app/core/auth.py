"""FastAPI dependencies for staff and borrower auth: who's signed in, role
gates, LO/Manager application scoping (plan.md Decision #11), and borrower
client ownership (CQ-015 spec.md AC6).

No endpoint outside `features/auth/staff` should read the `cq_staff_session`
cookie directly — everything else depends on `get_current_staff` (or the
`CurrentStaff` alias) instead. Symmetrically, no endpoint outside
`features/auth/borrower` should read `cq_borrower_session` directly; use
`get_current_borrower` / `CurrentBorrower`.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Cookie, Depends
from redis.asyncio import Redis
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.enums import UserRole
from app.core.errors import AuthenticationError, ForbiddenError, NotFoundError
from app.core.valkey import get_valkey
from app.features.applications.models import Application
from app.features.auth.models import BorrowerAccount, User
from app.features.auth.principal import Principal
from app.features.auth.sessions.service import COOKIE_NAMES, get_session_subject

_NOT_SIGNED_IN = "Not signed in"


async def _resolve_signed_in[R: (User, BorrowerAccount)](
    db: AsyncSession,
    valkey: Redis,
    *,
    principal: Principal,
    model: type[R],
    session_token: str | None,
) -> R:
    """Shared body of `get_current_staff` and `get_current_borrower`: only
    the cookie name (baked into `session_token` by its dependency), the
    Valkey principal namespace, and the row type differ between them.
    Raises `AuthenticationError` for a missing cookie, an expired/unknown
    session, or a session whose row has been deleted.
    """
    if session_token is None:
        raise AuthenticationError(_NOT_SIGNED_IN)

    subject_id = await get_session_subject(valkey, principal=principal, token=session_token)
    if subject_id is None:
        raise AuthenticationError(_NOT_SIGNED_IN)

    row = await db.get(model, uuid.UUID(subject_id))
    if row is None:
        raise AuthenticationError(_NOT_SIGNED_IN)
    return row


async def get_current_staff(
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAMES["staff"]),
) -> User:
    """Resolves the signed-in staff `User` from the `cq_staff_session`
    cookie. See `_resolve_signed_in` for the error cases."""
    return await _resolve_signed_in(
        db, valkey, principal="staff", model=User, session_token=session_token
    )


CurrentStaff = Annotated[User, Depends(get_current_staff)]


def require_roles(*roles: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
    """A dependency that 403s (`ForbiddenError`) unless the signed-in
    staff user's role is one of `roles`; otherwise returns that user."""

    async def _dependency(user: CurrentStaff) -> User:
        if user.role not in roles:
            raise ForbiddenError("You do not have access to this resource")
        return user

    return _dependency


async def get_current_borrower(
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAMES["borrower"]),
) -> BorrowerAccount:
    """Resolves the signed-in `BorrowerAccount` from the
    `cq_borrower_session` cookie. Same error shape as `get_current_staff`
    (see `_resolve_signed_in`), so a staff cookie presented here (or vice
    versa) 401s rather than 403s: the Valkey key is namespaced by
    principal (`sess:borrower:...` vs `sess:staff:...`), so a staff
    session token is simply not found under the borrower principal (AC5).
    """
    return await _resolve_signed_in(
        db, valkey, principal="borrower", model=BorrowerAccount, session_token=session_token
    )


CurrentBorrower = Annotated[BorrowerAccount, Depends(get_current_borrower)]


def ensure_borrower_owns_client(account: BorrowerAccount, client_id: uuid.UUID) -> None:
    """Raises `NotFoundError` (404, never 403 — Decision #11) unless
    `client_id` is `account`'s own client, so a borrower can't use the
    response to confirm that another client id exists."""
    if account.client_id != client_id:
        raise NotFoundError("Not found")


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


async def get_scoped_application(
    application_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> Application:
    """FastAPI dependency (phase-p2 merge, H3): resolves `application_id`
    only when it's in `user`'s `scope_applications` scope, else raises
    `NotFoundError` (404, never 403 -- Decision #11's style) so an LO can't
    use the response to confirm another LO's application id exists.

    Every pricing/pipeline route keyed directly by `application_id` (CQ-011's
    pipeline start/resume, CQ-013's scenario-create and field-value override/
    revert) depends on this instead of the old `get_current_lo_stub`.
    `pricing.scenarios.deps.ensure_scenario_in_scope` does the equivalent for
    routes keyed by `scenario_id` (scenarios have no owner of their own --
    scope is enforced through the application they belong to).
    """
    stmt = scope_applications(select(Application).where(Application.id == application_id), user)
    application = (await db.execute(stmt)).scalar_one_or_none()
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    return application
