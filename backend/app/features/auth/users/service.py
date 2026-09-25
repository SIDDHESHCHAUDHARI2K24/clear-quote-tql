"""Staff `User` creation and idempotent dev-user seeding (CQ-014 AC8).

`create_user` is the single entry point for making a `User` row — used by
`scripts/create_user.py` directly and by `seed_dev_users` below. It checks
for an existing row by normalized email rather than letting a unique-
constraint `IntegrityError` bubble up, so callers get the pinned `AppError`
shape (`ConflictError`) instead of a raw database exception. Like
`notifications/email/service.py::send_email`, it does not commit — the
caller owns the transaction.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.errors import ConflictError, ValidationAppError
from app.core.security import hash_password
from app.features.auth.models import User

MIN_PASSWORD_LENGTH = 8


def normalize_email(email: str) -> str:
    """Strips surrounding whitespace and lowercases, so lookups and the
    `users.email` unique constraint are effectively case-insensitive."""
    return email.strip().lower()


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

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
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


@dataclass(frozen=True)
class DevUserSpec:
    """One `DEV_USERS` entry — the fields `seed_dev_users` passes to `create_user`."""

    email: str
    role: UserRole
    full_name: str
    nmls: str | None = None
    title: str | None = None
    phone: str | None = None


# Decision #2 (plan.md): three demo staff logins seeded before CQ-010's
# `make demo-reset` exists, so the LO Console has something to log in as.
DEV_USERS: list[DevUserSpec] = [
    DevUserSpec(
        email="lo@clearquote.test",
        role=UserRole.LO,
        full_name="Jordan Avery",
        nmls="1000001",
        title="Loan Officer",
        phone="(317) 555-0101",
    ),
    DevUserSpec(
        email="manager@clearquote.test",
        role=UserRole.MANAGER,
        full_name="Morgan Blake",
        title="Sales Manager",
    ),
    DevUserSpec(
        email="admin@clearquote.test",
        role=UserRole.ADMIN,
        full_name="Riley Chen",
        title="Administrator",
    ),
]


async def seed_dev_users(db: AsyncSession, *, password: str) -> list[User]:
    """Creates any of `DEV_USERS` missing by email; leaves existing rows
    untouched (idempotent — a repeat run does not change an existing user's
    password hash, role or name). Returns all three `User` rows in
    `DEV_USERS` order. Does not commit.
    """
    users: list[User] = []
    for spec in DEV_USERS:
        existing = (
            await db.execute(select(User).where(User.email == spec.email))
        ).scalar_one_or_none()
        if existing is not None:
            users.append(existing)
            continue
        users.append(
            await create_user(
                db,
                email=spec.email,
                password=password,
                role=spec.role,
                full_name=spec.full_name,
                nmls=spec.nmls,
                title=spec.title,
                phone=spec.phone,
            )
        )
    return users
