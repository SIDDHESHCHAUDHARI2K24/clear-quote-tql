"""AC8 support: `create_user` — the single entry point `scripts/create_user.py`
uses to make a `User` row.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.errors import ConflictError, ValidationAppError
from app.core.security import verify_password
from app.features.auth.models import User
from app.features.auth.users.service import create_user, normalize_email


def test_normalize_email_strips_and_lowercases() -> None:
    assert normalize_email("  Jordan.Avery@ClearQuote.TEST  ") == "jordan.avery@clearquote.test"


async def test_create_user_happy_path_hashes_password_and_lowercases_email(
    db_session: AsyncSession,
) -> None:
    user = await create_user(
        db_session,
        email="  Jordan@ClearQuote.test  ",
        password="Sup3rSecret!",
        role=UserRole.LO,
        full_name="Jordan Avery",
        nmls="1000001",
        title="Loan Officer",
        phone="(317) 555-0101",
    )

    assert user.email == "jordan@clearquote.test"
    assert user.role == UserRole.LO
    assert user.full_name == "Jordan Avery"
    assert user.nmls == "1000001"
    assert user.title == "Loan Officer"
    assert user.phone == "(317) 555-0101"
    assert user.password_hash != "Sup3rSecret!"
    assert verify_password(user.password_hash, "Sup3rSecret!")

    row = (await db_session.execute(select(User).where(User.id == user.id))).scalar_one()
    assert row.email == "jordan@clearquote.test"


async def test_create_user_optional_fields_default_to_none(db_session: AsyncSession) -> None:
    user = await create_user(
        db_session,
        email="manager@clearquote.test",
        password="Sup3rSecret!",
        role=UserRole.MANAGER,
        full_name="Morgan Blake",
    )

    assert user.nmls is None
    assert user.title is None
    assert user.phone is None


async def test_create_user_duplicate_email_raises_conflict(db_session: AsyncSession) -> None:
    await create_user(
        db_session,
        email="dupe@clearquote.test",
        password="Sup3rSecret!",
        role=UserRole.LO,
        full_name="First User",
    )

    with pytest.raises(ConflictError):
        await create_user(
            db_session,
            email="DUPE@ClearQuote.test",
            password="AnotherSecret!",
            role=UserRole.ADMIN,
            full_name="Second User",
        )


async def test_create_user_short_password_raises_validation_error(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ValidationAppError):
        await create_user(
            db_session,
            email="short@clearquote.test",
            password="short1",
            role=UserRole.LO,
            full_name="Short Password",
        )

    row = (
        await db_session.execute(select(User).where(User.email == "short@clearquote.test"))
    ).scalar_one_or_none()
    assert row is None


async def test_create_user_race_on_insert_raises_conflict_not_integrity_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent caller can create the row after our pre-check but before
    our own insert; simulate that by making the pre-check miss the row that
    already exists, so the real failure comes from the `users.email` unique
    constraint on flush, not from the `existing is not None` branch."""
    await create_user(
        db_session,
        email="race@clearquote.test",
        password="Sup3rSecret!",
        role=UserRole.LO,
        full_name="First Writer",
    )

    class _EmptyResult:
        def scalar_one_or_none(self) -> None:
            return None

    original_execute = db_session.execute

    async def _fake_execute(*args: object, **kwargs: object) -> object:
        if args and "SELECT" in str(args[0]).upper():
            return _EmptyResult()
        return await original_execute(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(db_session, "execute", _fake_execute)

    with pytest.raises(ConflictError):
        await create_user(
            db_session,
            email="RACE@ClearQuote.test",
            password="AnotherSecret!",
            role=UserRole.ADMIN,
            full_name="Second Writer",
        )
