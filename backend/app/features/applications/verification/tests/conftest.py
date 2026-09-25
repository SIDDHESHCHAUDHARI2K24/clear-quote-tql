"""Local fixtures for the verification feature's integration tests.

`make_application` builds the minimum row graph (`users` -> `clients` ->
`applications`) every `run_and_persist`/`write_flag` test needs, satisfying
FK constraints without depending on CQ-010's seed data (not built yet).
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(occupancy: Occupancy = Occupancy.PRIMARY, **overrides: object) -> Application:
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

        application = Application(
            client_id=client.id, lo_id=lo.id, occupancy=occupancy, **overrides
        )
        db_session.add(application)
        await db_session.flush()
        return application

    return _make
