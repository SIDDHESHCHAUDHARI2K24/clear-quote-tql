"""CQ-030 AC6: the `stale-quote-check` Schedule exists after the worker's
startup registration and survives a restart without duplicating.

Runs against the Temporal dev server (`WorkflowEnvironment.start_local`),
because the time-skipping test server has no Schedule API.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast

import pytest
import pytest_asyncio
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
)
from temporalio.testing import WorkflowEnvironment

from app.core.config import get_settings
from app.workflows import worker as worker_module
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE
from app.workflows.stale_quote_check import StaleQuoteCheckWorkflow
from app.workflows.stale_schedule import (
    ScheduleRegistration,
    _matches,
    build_stale_schedule,
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


async def test_schedule_registration_failure_does_not_stop_the_worker(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Review m1: registration failing after connect is logged, and the
    pipeline worker still runs."""
    caplog.set_level(logging.ERROR, logger="app.workflows.worker")
    logging.getLogger("app.workflows.worker").disabled = False  # see test_worker_registration
    ran: list[bool] = []

    class _FakeWorker:
        async def run(self) -> None:
            ran.append(True)

    async def _fails(client: object) -> ScheduleRegistration:
        raise RuntimeError("schedule API unavailable")

    monkeypatch.setattr(worker_module, "build_worker", lambda client: _FakeWorker())
    monkeypatch.setattr(worker_module, "register_schedules", _fails)

    await worker_module.run_worker(cast(Client, object()))

    assert ran == [True]
    assert "stale quote schedule" in caplog.text
    assert "schedule API unavailable" in caplog.text


def test_schedule_policy_bounds_each_run() -> None:
    """Review M2: a run can never outlive its interval, a missed tick is
    caught up at most one interval late, and overlapping runs are skipped."""
    interval = timedelta(hours=1)
    schedule = build_stale_schedule(interval=interval, task_queue="cq-s16")

    action = schedule.action
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert action.execution_timeout is not None
    assert timedelta(0) < action.execution_timeout < interval
    assert schedule.policy.catchup_window == interval
    assert schedule.policy.overlap is ScheduleOverlapPolicy.SKIP
    assert _matches(schedule, interval=interval, task_queue="cq-s16")


@pytest.mark.parametrize(
    "policy",
    [
        SchedulePolicy(overlap=ScheduleOverlapPolicy.ALLOW_ALL, catchup_window=timedelta(hours=1)),
        SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP, catchup_window=timedelta(days=365)),
    ],
)
def test_matches_rejects_a_different_policy(policy: SchedulePolicy) -> None:
    interval = timedelta(hours=1)
    schedule = build_stale_schedule(interval=interval, task_queue="cq-s16")
    schedule.policy = policy
    assert not _matches(schedule, interval=interval, task_queue="cq-s16")


def test_matches_rejects_a_missing_execution_timeout() -> None:
    interval = timedelta(hours=1)
    schedule = build_stale_schedule(interval=interval, task_queue="cq-s16")
    assert isinstance(schedule.action, ScheduleActionStartWorkflow)
    schedule.action.execution_timeout = None
    assert not _matches(schedule, interval=interval, task_queue="cq-s16")


async def test_existing_schedule_with_old_policy_is_corrected(
    local_env: WorkflowEnvironment,
) -> None:
    """Review n1: a schedule registered before the policy change (overlap
    ALLOW_ALL, default catchup, no execution timeout) is updated in place."""
    queue = APPLICATION_PIPELINE_TASK_QUEUE
    schedule_id = stale_schedule_id(queue)
    interval = timedelta(hours=1)
    await local_env.client.create_schedule(
        schedule_id,
        Schedule(
            action=ScheduleActionStartWorkflow(
                StaleQuoteCheckWorkflow.run, id=f"{schedule_id}-run", task_queue=queue
            ),
            spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=interval)]),
            policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.ALLOW_ALL),
        ),
    )

    assert (
        await ensure_stale_quote_schedule(local_env.client, interval=interval, task_queue=queue)
        is ScheduleRegistration.UPDATED
    )
    description = await local_env.client.get_schedule_handle(schedule_id).describe()
    assert description.schedule.policy.overlap is ScheduleOverlapPolicy.SKIP
    assert description.schedule.policy.catchup_window == interval
    action = description.schedule.action
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert action.execution_timeout is not None and action.execution_timeout < interval
    assert (
        await ensure_stale_quote_schedule(local_env.client, interval=interval, task_queue=queue)
        is ScheduleRegistration.UNCHANGED
    )
