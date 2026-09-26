"""Guards for the workflow-test isolation fixtures in `conftest.py` (the
asyncpg "another operation is in progress" flake): retries are bounded
in tests, activity sessions serialise on `db_lock`, and teardown
terminates what a test left running."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client, WorkflowFailureError

from app.features.applications.models import Application
from app.workflows import activities
from app.workflows import db as workflow_db
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def test_default_retries_are_bounded_in_tests(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
    temporal_client: Client,
) -> None:
    """A transient failure under `DEFAULT_RETRY_POLICY` (unlimited in
    production) gives up after two attempts in tests instead of retrying
    into later tests."""
    application = await make_persona_application()
    calls: list[uuid.UUID] = []

    async def _always_fails(application_id: uuid.UUID, db: AsyncSession, **_: object) -> object:
        calls.append(application_id)
        raise ConnectionError("transient")

    monkeypatch.setattr(activities, "run_and_persist", _always_fails)

    with pytest.raises(WorkflowFailureError):
        await temporal_client.execute_workflow(
            ApplicationPipelineWorkflow.run,
            str(application.id),
            id=application_workflow_id(str(application.id)),
            task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
        )

    assert len(calls) == 2


async def test_activity_sessions_hold_the_test_lock(
    db_session: AsyncSession, db_lock: asyncio.Lock
) -> None:
    """While an activity session is open the test's `db_lock` is held, so
    test-side polling can never overlap it on the shared connection."""
    factory = cast(
        Callable[[], AbstractAsyncContextManager[AsyncSession]], workflow_db.session_factory
    )
    async with factory() as session:
        assert db_lock.locked()
        assert (await session.execute(select(1))).scalar_one() == 1
    assert not db_lock.locked()
