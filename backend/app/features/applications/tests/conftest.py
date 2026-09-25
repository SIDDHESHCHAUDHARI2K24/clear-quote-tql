"""Local fixtures for `applications/tests/test_pipeline_endpoints.py`: a
time-skipping `temporalio.testing.WorkflowEnvironment` (no real Temporal
server needed in CI) whose client overrides `get_temporal_client` for the
`client` (httpx) fixture's app instance. No worker is registered here —
`POST .../pipeline/start` only needs the server to *accept* the start
request (spec.md AC7 tests start/resume idempotency, not full pipeline
execution).

`make_application` builds the minimum row graph (`users` -> `clients` ->
`applications`) the pipeline routes' auth/scope tests need (phase-p2 merge,
H3), following `applications/verification/tests/conftest.py`'s established
pattern -- `lo=` lets a test own the application as a specific staff user
(e.g. a `make_staff_session` result's `.user`) for LO/Manager scoping.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client as ClientModel
from app.workflows.client import get_temporal_client


@pytest_asyncio.fixture
async def temporal_test_env() -> AsyncIterator[WorkflowEnvironment]:
    env = await WorkflowEnvironment.start_time_skipping()
    yield env
    await env.shutdown()


@pytest_asyncio.fixture
async def temporal_client(temporal_test_env: WorkflowEnvironment) -> Client:
    return temporal_test_env.client


@pytest_asyncio.fixture(autouse=True)
async def override_temporal_client_dep(
    app: FastAPI, temporal_client: Client
) -> AsyncIterator[None]:
    async def _override() -> Client:
        return temporal_client

    app.dependency_overrides[get_temporal_client] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_temporal_client, None)


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(
        occupancy: Occupancy = Occupancy.PRIMARY, lo: User | None = None
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

        client_row = ClientModel(
            full_name="Test Client",
            email=f"client-{uuid.uuid4()}@clearquote-demo.test",
            assigned_lo_id=lo.id,
        )
        db_session.add(client_row)
        await db_session.flush()

        application = Application(client_id=client_row.id, lo_id=lo.id, occupancy=occupancy)
        db_session.add(application)
        await db_session.flush()
        return application

    return _make
