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
    async def _make(lo: User | None = None, **overrides: object) -> Application:
        if lo is None:
            lo = User(
                email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
                password_hash="not-a-real-hash",
                role=UserRole.LO,
                full_name="Test LO",
            )
            db_session.add(lo)
            await db_session.flush()

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
    ) -> ActivityEvent:
        event = ActivityEvent(
            application_id=application.id,
            actor=actor,
            type=type,
            payload=payload,
            at=at or datetime.now(UTC),
        )
        db_session.add(event)
        await db_session.flush()
        return event

    return _make
