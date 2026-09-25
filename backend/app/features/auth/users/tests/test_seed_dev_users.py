"""AC8: `seed_dev_users.py` creates the three dev users; running it twice
leaves three users (and does not disturb the first run's password hash).

CQ-015 AC8 extends this for `seed_dev_borrowers`: the demo borrower's
client + account, an account for any other client missing one, and the
same idempotency guarantee.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.errors import ConflictError
from app.core.security import verify_password
from app.features.auth.models import BorrowerAccount, User
from app.features.auth.users import service as users_service
from app.features.auth.users.service import (
    DEMO_BORROWER_CLIENT_NAME,
    DEMO_BORROWER_EMAIL,
    DEV_USERS,
    seed_dev_borrowers,
    seed_dev_users,
)
from app.features.clients.models import Client


async def test_seed_dev_users_first_run_creates_three(db_session: AsyncSession) -> None:
    users = await seed_dev_users(db_session, password="Dem0Passw0rd!")

    assert len(users) == 3
    assert {user.email for user in users} == {spec.email for spec in DEV_USERS}
    assert {user.role for user in users} == {UserRole.LO, UserRole.MANAGER, UserRole.ADMIN}

    rows = (await db_session.execute(select(User))).scalars().all()
    assert len(rows) == 3
    for row in rows:
        assert verify_password(row.password_hash, "Dem0Passw0rd!")


async def test_seed_dev_users_second_run_is_idempotent(db_session: AsyncSession) -> None:
    first_run = await seed_dev_users(db_session, password="Dem0Passw0rd!")
    first_hashes = {user.email: user.password_hash for user in first_run}

    second_run = await seed_dev_users(db_session, password="ADifferentPassw0rd!")

    assert len(second_run) == 3
    rows = (await db_session.execute(select(User))).scalars().all()
    assert len(rows) == 3

    for row in rows:
        # Unchanged: still matches the first run's password, not the second's.
        assert row.password_hash == first_hashes[row.email]
        assert verify_password(row.password_hash, "Dem0Passw0rd!")
        assert not verify_password(row.password_hash, "ADifferentPassw0rd!")


async def test_seed_dev_users_roles_and_fields_correct(db_session: AsyncSession) -> None:
    users = await seed_dev_users(db_session, password="Dem0Passw0rd!")
    by_email = {user.email: user for user in users}

    lo = by_email["lo@clearquote.test"]
    assert lo.role == UserRole.LO
    assert lo.full_name == "Jordan Avery"
    assert lo.nmls == "1000001"
    assert lo.title == "Loan Officer"
    assert lo.phone == "(317) 555-0101"

    manager = by_email["manager@clearquote.test"]
    assert manager.role == UserRole.MANAGER
    assert manager.full_name == "Morgan Blake"
    assert manager.title == "Sales Manager"

    admin = by_email["admin@clearquote.test"]
    assert admin.role == UserRole.ADMIN
    assert admin.full_name == "Riley Chen"
    assert admin.title == "Administrator"


async def test_seed_dev_users_hashes_password_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three `DEV_USERS` share one `password` argument, so a fresh run
    must hash it exactly once (not once per user)."""
    calls: list[str] = []
    original_hash_password_async = users_service.hash_password_async

    async def _tracking_hash_password_async(password: str) -> str:
        calls.append(password)
        return await original_hash_password_async(password)

    monkeypatch.setattr(users_service, "hash_password_async", _tracking_hash_password_async)

    await seed_dev_users(db_session, password="Dem0Passw0rd!")

    assert calls == ["Dem0Passw0rd!"]


async def test_seed_dev_users_second_run_with_short_password_still_no_op(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the length check and the hash must only run for a user
    this call is actually about to insert. A rerun where every `DEV_USERS`
    entry already exists must stay a no-op — including with a `password`
    under `MIN_PASSWORD_LENGTH` — since `create_user`'s own length check
    was likewise only ever reached for a *missing* user."""
    await seed_dev_users(db_session, password="Dem0Passw0rd!")

    calls: list[str] = []
    original_hash_password_async = users_service.hash_password_async

    async def _tracking_hash_password_async(password: str) -> str:
        calls.append(password)
        return await original_hash_password_async(password)

    monkeypatch.setattr(users_service, "hash_password_async", _tracking_hash_password_async)

    users = await seed_dev_users(db_session, password="short1")

    assert len(users) == 3
    assert calls == []


async def test_seed_dev_borrowers_creates_demo_client_and_account(
    db_session: AsyncSession,
) -> None:
    await seed_dev_users(db_session, password="Dem0Passw0rd!")

    accounts = await seed_dev_borrowers(db_session, password="B0rrowerPassw0rd!")

    assert len(accounts) == 1
    assert accounts[0].email == DEMO_BORROWER_EMAIL
    assert accounts[0].password_hash is not None
    assert verify_password(accounts[0].password_hash, "B0rrowerPassw0rd!")
    assert accounts[0].email_verified_at is not None

    demo_client = (
        await db_session.execute(select(Client).where(Client.email == DEMO_BORROWER_EMAIL))
    ).scalar_one()
    assert demo_client.full_name == DEMO_BORROWER_CLIENT_NAME

    lo = (
        await db_session.execute(select(User).where(User.email == "lo@clearquote.test"))
    ).scalar_one()
    assert demo_client.assigned_lo_id == lo.id


async def test_seed_dev_borrowers_second_run_is_idempotent(db_session: AsyncSession) -> None:
    await seed_dev_users(db_session, password="Dem0Passw0rd!")
    first_run = await seed_dev_borrowers(db_session, password="B0rrowerPassw0rd!")
    first_hash = first_run[0].password_hash

    second_run = await seed_dev_borrowers(db_session, password="ADifferentPassw0rd!")

    assert second_run == []
    demo_accounts = (
        (
            await db_session.execute(
                select(BorrowerAccount).where(BorrowerAccount.email == DEMO_BORROWER_EMAIL)
            )
        )
        .scalars()
        .all()
    )
    assert len(demo_accounts) == 1
    assert demo_accounts[0].password_hash == first_hash
    assert demo_accounts[0].password_hash is not None
    assert verify_password(demo_accounts[0].password_hash, "B0rrowerPassw0rd!")


async def test_seed_dev_borrowers_hashes_password_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every account created this run shares one `password` argument, so a
    run creating more than one account (the demo borrower plus another
    client) must hash it exactly once, not once per account."""
    users = await seed_dev_users(db_session, password="Dem0Passw0rd!")
    lo = next(user for user in users if user.role == UserRole.LO)
    db_session.add(
        Client(full_name="Other Client", email="hash-once@clearquote.test", assigned_lo_id=lo.id)
    )
    await db_session.flush()

    calls: list[str] = []
    original_hash_password_async = users_service.hash_password_async

    async def _tracking_hash_password_async(password: str) -> str:
        calls.append(password)
        return await original_hash_password_async(password)

    monkeypatch.setattr(users_service, "hash_password_async", _tracking_hash_password_async)

    accounts = await seed_dev_borrowers(db_session, password="B0rrowerPassw0rd!")

    assert len(accounts) == 2
    assert calls == ["B0rrowerPassw0rd!"]


async def test_seed_dev_borrowers_second_run_does_not_hash(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A no-op rerun (every client already has an account) must not hash
    `password` at all."""
    await seed_dev_users(db_session, password="Dem0Passw0rd!")
    await seed_dev_borrowers(db_session, password="B0rrowerPassw0rd!")

    calls: list[str] = []
    original_hash_password_async = users_service.hash_password_async

    async def _tracking_hash_password_async(password: str) -> str:
        calls.append(password)
        return await original_hash_password_async(password)

    monkeypatch.setattr(users_service, "hash_password_async", _tracking_hash_password_async)

    second_run = await seed_dev_borrowers(db_session, password="ADifferentPassw0rd!")

    assert second_run == []
    assert calls == []

    clients = (
        (await db_session.execute(select(Client).where(Client.email == DEMO_BORROWER_EMAIL)))
        .scalars()
        .all()
    )
    assert len(clients) == 1


async def test_seed_dev_borrowers_creates_account_for_existing_client_without_one(
    db_session: AsyncSession,
) -> None:
    users = await seed_dev_users(db_session, password="Dem0Passw0rd!")
    lo = next(user for user in users if user.role == UserRole.LO)

    other_client = Client(
        full_name="Other Client", email="other-client@clearquote.test", assigned_lo_id=lo.id
    )
    db_session.add(other_client)
    await db_session.flush()

    accounts = await seed_dev_borrowers(db_session, password="B0rrowerPassw0rd!")

    emails = {account.email for account in accounts}
    assert emails == {DEMO_BORROWER_EMAIL, "other-client@clearquote.test"}
    other_account = next(a for a in accounts if a.email == "other-client@clearquote.test")
    assert other_account.client_id == other_client.id
    assert other_account.password_hash is not None
    assert verify_password(other_account.password_hash, "B0rrowerPassw0rd!")


async def test_seed_dev_borrowers_without_lo_raises_conflict(db_session: AsyncSession) -> None:
    with pytest.raises(ConflictError):
        await seed_dev_borrowers(db_session, password="B0rrowerPassw0rd!")


async def test_seed_dev_borrowers_skips_clients_that_collide_on_normalized_email(
    db_session: AsyncSession,
) -> None:
    """`clients.email` isn't unique — two clients whose emails normalize to
    the same value must not abort the whole seed run (regression: the
    losing insert's `IntegrityError` is caught and that one client is
    skipped, not raised)."""
    users = await seed_dev_users(db_session, password="Dem0Passw0rd!")
    lo = next(user for user in users if user.role == UserRole.LO)

    db_session.add(Client(full_name="Dupe One", email="dupe@clearquote.test", assigned_lo_id=lo.id))
    db_session.add(Client(full_name="Dupe Two", email="DUPE@ClearQuote.test", assigned_lo_id=lo.id))
    db_session.add(
        Client(full_name="Unique", email="unique-client@clearquote.test", assigned_lo_id=lo.id)
    )
    await db_session.flush()

    accounts = await seed_dev_borrowers(db_session, password="B0rrowerPassw0rd!")

    emails = {account.email for account in accounts}
    assert emails == {DEMO_BORROWER_EMAIL, "dupe@clearquote.test", "unique-client@clearquote.test"}

    dupe_accounts = (
        (
            await db_session.execute(
                select(BorrowerAccount).where(BorrowerAccount.email == "dupe@clearquote.test")
            )
        )
        .scalars()
        .all()
    )
    assert len(dupe_accounts) == 1
