"""AC4: exactly 2 LO, 1 Manager, 1 Admin, each with an argon2 password_hash.

Review round 1, finding #3: no plaintext password lives in `seed/users.yaml`
any more -- `seed_users` reads `SEED_STAFF_PASSWORD` from the environment
(set for the whole test session by `seed/tests/conftest.py`).

phase-p2 merge (X1): `seed_users` hashes with `app.core.security.hash_password`
(argon2), the same primitive real staff login verifies against via
`verify_password` -- not bcrypt, which `core.security.verify_password`
always rejects.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.security import hash_password, verify_password
from app.features.auth.models import User
from seed.loader import MissingStaffPasswordError, load_users_fixture, seed_users


async def test_seed_users_creates_exactly_2_lo_1_manager_1_admin(db_session: AsyncSession) -> None:
    await seed_users(db_session)

    users = (await db_session.execute(select(User))).scalars().all()
    by_role: dict[UserRole, list[User]] = {}
    for user in users:
        by_role.setdefault(user.role, []).append(user)

    assert len(by_role.get(UserRole.LO, [])) == 2
    assert len(by_role.get(UserRole.MANAGER, [])) == 1
    assert len(by_role.get(UserRole.ADMIN, [])) == 1


async def test_seed_users_password_hashes_are_real_argon2_of_env_password(
    db_session: AsyncSession,
) -> None:
    await seed_users(db_session)

    plaintext = get_settings().seed_staff_password
    assert plaintext is not None
    fixture_emails = {row["email"] for row in load_users_fixture()}
    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == len(fixture_emails)

    for user in users:
        assert user.email in fixture_emails
        assert user.password_hash != plaintext
        assert user.password_hash.startswith("$argon2")
        assert verify_password(user.password_hash, plaintext)


async def test_seed_users_hashes_password_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Argon2 is deliberately CPU-expensive -- `seed_users` must hash the
    shared demo password once, not once per fixture row."""
    calls = 0

    def _counting_hash_password(plain: str) -> str:
        nonlocal calls
        calls += 1
        return hash_password(plain)

    monkeypatch.setattr("seed.loader.hash_password", _counting_hash_password)

    await seed_users(db_session)

    assert calls == 1


async def test_seed_users_fails_clearly_when_password_setting_unset(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    unset_settings = get_settings().model_copy(update={"seed_staff_password": None})
    monkeypatch.setattr("seed.loader.get_settings", lambda: unset_settings)

    with pytest.raises(MissingStaffPasswordError):
        await seed_users(db_session)
