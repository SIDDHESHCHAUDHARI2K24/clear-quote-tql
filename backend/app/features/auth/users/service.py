"""Staff `User` creation (CQ-014 AC8).

`create_user` is the single entry point for making a `User` row — used by
`scripts/create_user.py`. It checks for an existing row by normalized email
rather than letting a unique-constraint `IntegrityError` bubble up, so
callers get the pinned `AppError` shape (`ConflictError`) instead of a raw
database exception. Like `notifications/email/service.py::send_email`, it
does not commit — the caller owns the transaction.

phase-p2 merge (X3): the dev-user seeding this module used to hold
(`DEV_USERS` / `seed_dev_users` / `seed_dev_borrowers`, and
`backend/scripts/seed_dev_users.py`) is retired in favour of `make
demo-reset` (`seed/loader.py::seed_users` / `seed_borrower_accounts`, driven
by `seed/users.yaml` and the persona fixtures) — one seed path instead of
two competing sets of demo users.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.errors import ConflictError, ValidationAppError
from app.core.security import hash_password_async
from app.features.auth.models import User

MIN_PASSWORD_LENGTH = 8


def normalize_email(email: str) -> str:
    """Strips surrounding whitespace and lowercases, so lookups and the
    `users.email` unique constraint are effectively case-insensitive."""
    return email.strip().lower()


async def _insert_user(
    db: AsyncSession,
    *,
    normalized_email: str,
    password_hash: str,
    role: UserRole,
    full_name: str,
    nmls: str | None = None,
    title: str | None = None,
    phone: str | None = None,
) -> User:
    """The SAVEPOINT insert `create_user` uses, split out so the flush and
    its `IntegrityError` -> `ConflictError` translation live in one place.
    Does not commit."""
    user = User(
        email=normalized_email,
        password_hash=password_hash,
        role=role,
        full_name=full_name,
        nmls=nmls,
        title=title,
        phone=phone,
    )
    try:
        async with db.begin_nested():
            db.add(user)
            await db.flush()
    except IntegrityError as exc:
        raise ConflictError(f"A user with email {normalized_email} already exists.") from exc
    return user


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: UserRole,
    full_name: str,
    nmls: str | None = None,
    title: str | None = None,
    phone: str | None = None,
) -> User:
    """Creates and flushes a `User` row. Does not commit.

    Raises `ConflictError` if a user with `email` (normalized) already
    exists, or `ValidationAppError` if `password` is shorter than
    `MIN_PASSWORD_LENGTH`.

    The pre-check below narrows the common case to a clean `ConflictError`,
    but two concurrent callers can both pass it before either flushes
    (check-then-insert race) — the `users.email` unique constraint is the
    real guard. The insert runs inside a SAVEPOINT (`begin_nested`) so a
    losing `IntegrityError` only rolls back this insert, not the caller's
    whole transaction, and is converted to the same `ConflictError`.
    """
    normalized_email = normalize_email(email)

    existing = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"A user with email {normalized_email} already exists.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationAppError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    return await _insert_user(
        db,
        normalized_email=normalized_email,
        password_hash=await hash_password_async(password),
        role=role,
        full_name=full_name,
        nmls=nmls,
        title=title,
        phone=phone,
    )
