"""AC6: `ensure_borrower_owns_client` returns 404 (never 403) for another
client's id and passes for the borrower's own."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ensure_borrower_owns_client
from app.core.enums import UserRole
from app.core.errors import NotFoundError
from app.features.auth.models import BorrowerAccount, User
from app.features.clients.models import Client


async def _make_client(db_session: AsyncSession, *, lo: User) -> Client:
    client = Client(
        full_name="Test Client", email=f"client-{uuid.uuid4()}@example.com", assigned_lo_id=lo.id
    )
    db_session.add(client)
    await db_session.flush()
    return client


async def _make_account(db_session: AsyncSession, *, client: Client) -> BorrowerAccount:
    account = BorrowerAccount(client_id=client.id, email=client.email)
    db_session.add(account)
    await db_session.flush()
    return account


async def test_ensure_borrower_owns_client_passes_for_own_client(
    db_session: AsyncSession,
) -> None:
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote.test",
        password_hash="x",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()

    client = await _make_client(db_session, lo=lo)
    account = await _make_account(db_session, client=client)

    # Does not raise.
    ensure_borrower_owns_client(account, client.id)


async def test_ensure_borrower_owns_client_404s_for_another_client(
    db_session: AsyncSession,
) -> None:
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote.test",
        password_hash="x",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()

    own_client = await _make_client(db_session, lo=lo)
    other_client = await _make_client(db_session, lo=lo)
    account = await _make_account(db_session, client=own_client)

    with pytest.raises(NotFoundError):
        ensure_borrower_owns_client(account, other_client.id)
