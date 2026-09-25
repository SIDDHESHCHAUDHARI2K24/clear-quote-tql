"""phase-p2 merge (X4): `seed.loader.seed_borrower_accounts` gives every
persona client a `borrower_accounts` row when `SEED_BORROWER_PASSWORD` is
set, and skips (never fails) when it's unset -- borrower login is optional
for the LO demo.
"""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_password
from app.features.auth.models import BorrowerAccount
from seed.loader import seed_borrower_accounts
from seed.tests.conftest import SeededBase


async def test_seed_borrower_accounts_creates_one_per_persona_client(
    seeded_base: SeededBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings().model_copy(update={"seed_borrower_password": "test-only-borrower-pw"})
    monkeypatch.setattr("seed.loader.get_settings", lambda: settings)

    client_ids = [r.client_id for r in seeded_base.persona_results]
    assert len(client_ids) == 10

    result = await seed_borrower_accounts(seeded_base.db, client_ids=client_ids)

    assert set(result.account_ids) == set(client_ids)
    accounts = (
        (
            await seeded_base.db.execute(
                select(BorrowerAccount).where(BorrowerAccount.client_id.in_(client_ids))
            )
        )
        .scalars()
        .all()
    )
    assert len(accounts) == 10
    for account in accounts:
        assert account.email_verified_at is not None
        assert account.password_hash is not None
        assert verify_password(account.password_hash, "test-only-borrower-pw")


async def test_seed_borrower_accounts_skips_when_password_unset(
    seeded_base: SeededBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings().model_copy(update={"seed_borrower_password": None})
    monkeypatch.setattr("seed.loader.get_settings", lambda: settings)

    client_ids = [r.client_id for r in seeded_base.persona_results]

    result = await seed_borrower_accounts(seeded_base.db, client_ids=client_ids)

    assert result.account_ids == {}
    accounts = (
        (
            await seeded_base.db.execute(
                select(BorrowerAccount).where(BorrowerAccount.client_id.in_(client_ids))
            )
        )
        .scalars()
        .all()
    )
    assert accounts == []


async def test_seed_borrower_accounts_is_idempotent(
    seeded_base: SeededBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings().model_copy(update={"seed_borrower_password": "test-only-borrower-pw"})
    monkeypatch.setattr("seed.loader.get_settings", lambda: settings)

    client_ids = [r.client_id for r in seeded_base.persona_results]

    first = await seed_borrower_accounts(seeded_base.db, client_ids=client_ids)
    second = await seed_borrower_accounts(seeded_base.db, client_ids=client_ids)

    assert first.account_ids == second.account_ids
    accounts = (
        (
            await seeded_base.db.execute(
                select(BorrowerAccount).where(BorrowerAccount.client_id.in_(client_ids))
            )
        )
        .scalars()
        .all()
    )
    assert len(accounts) == 10
