"""CQ-030 AC6: the `stale-quote-check` Schedule exists after the worker's
startup registration and survives a restart without duplicating.

Runs against the Temporal dev server (`WorkflowEnvironment.start_local`),
because the time-skipping test server has no Schedule API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from temporalio.client import ScheduleActionStartWorkflow
from temporalio.testing import WorkflowEnvironment

from app.core.config import get_settings
from app.workflows import worker as worker_module
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE
from app.workflows.stale_schedule import (
    ScheduleRegistration,
    ensure_stale_quote_schedule,
    stale_schedule_id,
)


@pytest_asyncio.fixture
async def local_env() -> AsyncIterator[WorkflowEnvironment]:
    env = await WorkflowEnvironment.start_local()
    try:
        yield env
    finally:
        await env.shutdown()


async def _schedule_ids(env: WorkflowEnvironment) -> list[str]:
    return [s.id async for s in await env.client.list_schedules()]


async def test_schedule_registered_once(local_env: WorkflowEnvironment) -> None:
    schedule_id = stale_schedule_id(APPLICATION_PIPELINE_TASK_QUEUE)
    interval = timedelta(seconds=get_settings().stale_check_interval_seconds)

    # First worker start: the schedule is created, and the worker built
    # with the stale workflow registered starts cleanly.
    assert await worker_module.register_schedules(local_env.client) is ScheduleRegistration.CREATED
    async with worker_module.build_worker(local_env.client):
        pass

    # Restart: registration is a no-op; still exactly one schedule.
    assert (
        await worker_module.register_schedules(local_env.client) is ScheduleRegistration.UNCHANGED
    )
    assert (await _schedule_ids(local_env)).count(schedule_id) == 1

    description = await local_env.client.get_schedule_handle(schedule_id).describe()
    action = description.schedule.action
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert action.workflow == "StaleQuoteCheckWorkflow"
    assert action.task_queue == APPLICATION_PIPELINE_TASK_QUEUE
    assert description.schedule.spec.intervals[0].every == interval


async def test_schedule_updated_when_interval_changes(local_env: WorkflowEnvironment) -> None:
    queue = APPLICATION_PIPELINE_TASK_QUEUE
    schedule_id = stale_schedule_id(queue)
    hourly = timedelta(hours=1)
    minutely = timedelta(minutes=1)

    assert (
        await ensure_stale_quote_schedule(local_env.client, interval=hourly, task_queue=queue)
        is ScheduleRegistration.CREATED
    )
    assert (
        await ensure_stale_quote_schedule(local_env.client, interval=minutely, task_queue=queue)
        is ScheduleRegistration.UPDATED
    )
    assert (
        await ensure_stale_quote_schedule(local_env.client, interval=minutely, task_queue=queue)
        is ScheduleRegistration.UNCHANGED
    )

    assert (await _schedule_ids(local_env)).count(schedule_id) == 1
    description = await local_env.client.get_schedule_handle(schedule_id).describe()
    assert description.schedule.spec.intervals[0].every == minutely


@pytest.mark.parametrize(
    ("queue", "expected"),
    [("clear-quote-pipeline", "stale-quote-check"), ("cq-s16", "stale-quote-check-cq-s16")],
)
def test_schedule_id_per_task_queue(queue: str, expected: str) -> None:
    assert stale_schedule_id(queue) == expected
