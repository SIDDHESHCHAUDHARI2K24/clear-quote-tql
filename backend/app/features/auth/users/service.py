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
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.errors import ConflictError, ValidationAppError
from app.core.security import hash_password
from app.features.auth.models import BorrowerAccount, User
from app.features.clients.models import Client

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


# CQ-015 Decision #12: the demo borrower's client + account.
DEMO_BORROWER_EMAIL = "borrower@clearquote.test"
DEMO_BORROWER_CLIENT_NAME = "Casey Morgan"
DEMO_BORROWER_LO_EMAIL = "lo@clearquote.test"


async def _ensure_demo_borrower_client(db: AsyncSession) -> Client:
    """Creates the demo borrower's client ("Casey Morgan", assigned to
    `lo@clearquote.test`) if it doesn't already exist. Does not commit."""
    client = (
        await db.execute(select(Client).where(Client.email == DEMO_BORROWER_EMAIL))
    ).scalar_one_or_none()
    if client is not None:
        return client

    lo = (
        await db.execute(select(User).where(User.email == DEMO_BORROWER_LO_EMAIL))
    ).scalar_one_or_none()
    if lo is None:
        raise ConflictError(
            f"No {DEMO_BORROWER_LO_EMAIL} user to assign the demo borrower's client to — "
            "run seed_dev_users first."
        )
    client = Client(
        full_name=DEMO_BORROWER_CLIENT_NAME, email=DEMO_BORROWER_EMAIL, assigned_lo_id=lo.id
    )
    db.add(client)
    await db.flush()
    return client


async def seed_dev_borrowers(db: AsyncSession, *, password: str) -> list[BorrowerAccount]:
    """CQ-015 Decision #12: ensures the demo borrower's client exists, then
    creates a `BorrowerAccount` (`password`, `email_verified_at` set to
    now) for every client — the demo one included — that doesn't already
    have one.

    Idempotent: a repeat run creates neither a second demo client nor a
    second account for any client, and never touches an existing account's
    `password_hash`. Returns only the accounts created by *this* call
    (empty once every client already has one). Does not commit.

    `clients.email` is not unique (unlike `borrower_accounts.email`), so
    two clients whose emails normalize to the same value — or a client
    whose email already belongs to another client's account — would
    otherwise abort the whole run on the first `IntegrityError`. Each
    insert runs in its own SAVEPOINT (mirroring `create_user`), and a
    losing one is skipped rather than crashing the seed for every other
    client.
    """
    await _ensure_demo_borrower_client(db)

    clients_missing_accounts = (
        (
            await db.execute(
                select(Client)
                .outerjoin(BorrowerAccount, BorrowerAccount.client_id == Client.id)
                .where(BorrowerAccount.id.is_(None))
                .order_by(Client.created_at, Client.id)
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    created: list[BorrowerAccount] = []
    for client in clients_missing_accounts:
        account = BorrowerAccount(
            client_id=client.id,
            email=normalize_email(client.email),
            password_hash=hash_password(password),
            email_verified_at=now,
        )
        try:
            async with db.begin_nested():
                db.add(account)
                await db.flush()
        except IntegrityError:
            continue
        created.append(account)
    return created
