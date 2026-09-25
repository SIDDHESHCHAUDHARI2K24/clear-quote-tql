"""AC8: `seed_dev_users.py` creates the three dev users; running it twice
leaves three users (and does not disturb the first run's password hash).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.security import verify_password
from app.features.auth.models import User
from app.features.auth.users.service import DEV_USERS, seed_dev_users


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
