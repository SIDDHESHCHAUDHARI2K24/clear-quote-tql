"""P5/P6 foundation (E17): `seed_no_application_borrower` creates one
verified borrower account with a client and no application when
`SEED_BORROWER_PASSWORD` is set (CQ-031 AC4, CQ-034 AC5)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import verify_password
from app.features.applications.models import Application
from app.features.auth.models import BorrowerAccount
from app.features.clients.models import Client
from seed.loader import (
    NO_APPLICATION_BORROWER_EMAIL,
    seed_no_application_borrower,
    seed_users,
)


def _use_password(monkeypatch: pytest.MonkeyPatch, password: str | None) -> None:
    settings = get_settings().model_copy(update={"seed_borrower_password": password})
    monkeypatch.setattr("seed.loader.get_settings", lambda: settings)


async def _account_count(db: AsyncSession) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(BorrowerAccount)
            .where(BorrowerAccount.email == NO_APPLICATION_BORROWER_EMAIL)
        )
    ).scalar_one()


async def test_creates_account_and_client_without_application(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = await seed_users(db_session)
    _use_password(monkeypatch, "test-only-borrower-pw")

    account_id = await seed_no_application_borrower(db_session)

    assert account_id is not None
    account = await db_session.get(BorrowerAccount, account_id)
    assert account is not None
    assert account.email == NO_APPLICATION_BORROWER_EMAIL
    assert account.email_verified_at is not None
    assert account.password_hash is not None
    assert verify_password(account.password_hash, "test-only-borrower-pw")

    client = await db_session.get(Client, account.client_id)
    assert client is not None
    assert client.assigned_lo_id in users.lo_ids
    application_count = (
        await db_session.execute(
            select(func.count()).select_from(Application).where(Application.client_id == client.id)
        )
    ).scalar_one()
    assert application_count == 0


async def test_skipped_when_password_unset(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_users(db_session)
    _use_password(monkeypatch, None)

    assert await seed_no_application_borrower(db_session) is None
    assert await _account_count(db_session) == 0


async def test_is_idempotent(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    await seed_users(db_session)
    _use_password(monkeypatch, "test-only-borrower-pw")

    first = await seed_no_application_borrower(db_session)
    second = await seed_no_application_borrower(db_session)

    assert first == second
    assert await _account_count(db_session) == 1
