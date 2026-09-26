"""Local fixtures for `applications/timeline/tests/` (established per
subpackage `make_application`/`make_activity_event` pattern, see
`applications/summary/tests/conftest.py`)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import User
from app.features.clients.models import Client


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(
        lo: User | None = None, client: Client | None = None, **overrides: object
    ) -> Application:
        if lo is None:
            lo = User(
                email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
                password_hash="not-a-real-hash",
                role=UserRole.LO,
                full_name="Test LO",
            )
            db_session.add(lo)
            await db_session.flush()

        if client is None:
            # `client` lets two calls share one `Client` (review round 2,
            # applications/timeline/tests/test_service.py's
            # `list_activity_for_applications` tests) -- defaults to a
            # fresh client per call, same as before.
            client = Client(
                full_name="Test Client",
                email=f"client-{uuid.uuid4()}@clearquote-demo.test",
                assigned_lo_id=lo.id,
            )
            db_session.add(client)
            await db_session.flush()

        defaults: dict[str, object] = {"occupancy": Occupancy.PRIMARY, "program": "Conventional"}
        defaults.update(overrides)
        application = Application(client_id=client.id, lo_id=lo.id, **defaults)
        db_session.add(application)
        await db_session.flush()
        return application

    return _make


@pytest_asyncio.fixture
async def make_client(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Client]]:
    async def _make(lo: User) -> Client:
        client = Client(
            full_name="Test Client",
            email=f"client-{uuid.uuid4()}@clearquote-demo.test",
            assigned_lo_id=lo.id,
        )
        db_session.add(client)
        await db_session.flush()
        return client

    return _make


@pytest_asyncio.fixture
async def make_lo(db_session: AsyncSession) -> Callable[..., Awaitable[User]]:
    async def _make() -> User:
        lo = User(
            email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
            password_hash="not-a-real-hash",
            role=UserRole.LO,
            full_name="Test LO",
        )
        db_session.add(lo)
        await db_session.flush()
        return lo

    return _make


@pytest_asyncio.fixture
async def make_activity_event(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[ActivityEvent]]:
    async def _make(
        application: Application,
        type: str,  # noqa: A002
        *,
        actor: str = "system",
        payload: object = None,
        at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> ActivityEvent:
        event = ActivityEvent(
            application_id=application.id,
            actor=actor,
            type=type,
            payload=payload,
            at=at or datetime.now(UTC),
        )
        if created_at is not None:
            # Overrides the `created_at` server default (Postgres `now()`,
            # fixed for the whole test transaction) so a test can simulate
            # two rows inserted at different real moments under one frozen
            # `at` (U3 review minor: `at DESC` alone ties when `CLOCK_NOW`
            # is frozen, so `list_activity`/`list_activity_for_applications`
            # add `created_at DESC` as the tiebreak).
            event.created_at = created_at
        db_session.add(event)
        await db_session.flush()
        return event

    return _make
