"""AC4: exactly 2 LO, 1 Manager, 1 Admin, each with a bcrypt password_hash."""

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.auth.models import User
from seed.loader import load_users_fixture, seed_users


async def test_seed_users_creates_exactly_2_lo_1_manager_1_admin(db_session: AsyncSession) -> None:
    await seed_users(db_session)

    users = (await db_session.execute(select(User))).scalars().all()
    by_role: dict[UserRole, list[User]] = {}
    for user in users:
        by_role.setdefault(user.role, []).append(user)

    assert len(by_role.get(UserRole.LO, [])) == 2
    assert len(by_role.get(UserRole.MANAGER, [])) == 1
    assert len(by_role.get(UserRole.ADMIN, [])) == 1


async def test_seed_users_password_hashes_are_real_bcrypt(db_session: AsyncSession) -> None:
    await seed_users(db_session)

    fixture_rows = {row["email"]: row["password"] for row in load_users_fixture()}
    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == len(fixture_rows)

    for user in users:
        plaintext = fixture_rows[user.email]
        assert user.password_hash != plaintext
        assert user.password_hash.startswith("$2b$")
        assert bcrypt.checkpw(plaintext.encode("utf-8"), user.password_hash.encode("ascii"))
