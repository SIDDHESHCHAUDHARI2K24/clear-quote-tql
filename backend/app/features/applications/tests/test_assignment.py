"""`applications.assignment.least_loaded_lo_id` (P5/P6 foundation, E15)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.applications.assignment import least_loaded_lo_id
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client


async def _make_user(db: AsyncSession, name: str, role: UserRole = UserRole.LO) -> User:
    user = User(
        email=f"{uuid.uuid4()}@clearquote.test", password_hash="x", role=role, full_name=name
    )
    db.add(user)
    await db.flush()
    return user


async def _give_applications(db: AsyncSession, lo: User, statuses: list[ApplicationStatus]) -> None:
    client = Client(full_name="C", email=f"{uuid.uuid4()}@x.test", assigned_lo_id=lo.id)
    db.add(client)
    await db.flush()
    for status in statuses:
        db.add(Application(client_id=client.id, lo_id=lo.id, status=status))
    await db.flush()


async def test_no_lo_returns_none(db_session: AsyncSession) -> None:
    await _make_user(db_session, "Only A Manager", UserRole.MANAGER)
    assert await least_loaded_lo_id(db_session) is None


async def test_fewest_active_applications_wins(db_session: AsyncSession) -> None:
    busy = await _make_user(db_session, "Aaron Busy")
    quiet = await _make_user(db_session, "Zed Quiet")
    await _give_applications(db_session, busy, [ApplicationStatus.PRICED, ApplicationStatus.INTAKE])
    await _give_applications(db_session, quiet, [ApplicationStatus.SENT])

    assert await least_loaded_lo_id(db_session) == quiet.id


async def test_withdrawn_and_closed_do_not_count(db_session: AsyncSession) -> None:
    alpha = await _make_user(db_session, "Alpha LO")
    beta = await _make_user(db_session, "Beta LO")
    await _give_applications(
        db_session,
        alpha,
        [ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED, ApplicationStatus.CLOSED],
    )
    await _give_applications(db_session, beta, [ApplicationStatus.NEEDS_ATTENTION])

    # alpha has 0 active (3 inactive), beta has 1 active.
    assert await least_loaded_lo_id(db_session) == alpha.id


async def test_tie_is_broken_alphabetically_by_name(db_session: AsyncSession) -> None:
    await _make_user(db_session, "Morgan Tie")
    first = await _make_user(db_session, "Casey Tie")
    await _make_user(db_session, "Riley Tie")

    assert await least_loaded_lo_id(db_session) == first.id


async def test_managers_and_admins_are_never_chosen(db_session: AsyncSession) -> None:
    await _make_user(db_session, "Aardvark Manager", UserRole.MANAGER)
    await _make_user(db_session, "Aardvark Admin", UserRole.ADMIN)
    lo = await _make_user(db_session, "Zulu LO")
    await _give_applications(db_session, lo, [ApplicationStatus.PRICED] * 5)

    assert await least_loaded_lo_id(db_session) == lo.id
