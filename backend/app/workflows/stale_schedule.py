"""CQ-030: idempotent registration of the Temporal Schedule that runs
`StaleQuoteCheckWorkflow` (spec.md "The worker registers the schedule on
startup if it does not exist"; AC6).

`ensure_stale_quote_schedule` describes the schedule and then:
- creates it if it is missing;
- updates it in place if its interval, task queue, workflow, run timeout,
  overlap policy or catch-up window differs;
- otherwise leaves it alone.

A lost create race (two workers starting at once) surfaces as
`ScheduleAlreadyRunningError` and falls through to the update check, so a
restart never duplicates the schedule.

Schedule ids are namespace-global, and every worktree slot shares one
Temporal namespace with its own task queue. So the id is
`stale-quote-check` on the default queue and `stale-quote-check-<queue>`
on any other queue (plan.md decision #9); one slot's worker never rewrites
another slot's schedule.
"""

from __future__ import annotations

import enum
import logging
from datetime import timedelta

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.service import RPCError, RPCStatusCode

from app.workflows.stale_quote_check import StaleQuoteCheckWorkflow

logger = logging.getLogger(__name__)

STALE_QUOTE_SCHEDULE_ID = "stale-quote-check"
DEFAULT_TASK_QUEUE = "clear-quote-pipeline"
"""`.env.example`'s `TEMPORAL_TASK_QUEUE`: the one queue whose schedule
keeps the bare spec name."""


class ScheduleRegistration(enum.StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


def stale_schedule_id(task_queue: str) -> str:
    if task_queue == DEFAULT_TASK_QUEUE:
        return STALE_QUOTE_SCHEDULE_ID
    return f"{STALE_QUOTE_SCHEDULE_ID}-{task_queue}"


def run_execution_timeout(interval: timedelta) -> timedelta:
    """Review M2: a run (all its activity attempts included) is cut off at
    90% of the interval, so it never overlaps the next tick."""
    return interval * 9 // 10


def build_stale_schedule(*, interval: timedelta, task_queue: str) -> Schedule:
    return Schedule(
        action=ScheduleActionStartWorkflow(
            StaleQuoteCheckWorkflow.run,
            id=f"{stale_schedule_id(task_queue)}-run",
            task_queue=task_queue,
            execution_timeout=run_execution_timeout(interval),
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=interval)]),
        # A tick missed while the server was down runs at most one
        # interval late; older ones are dropped (the job is idempotent).
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP, catchup_window=interval),
    )


def _matches(schedule: Schedule, *, interval: timedelta, task_queue: str) -> bool:
    """Whether an existing schedule already equals `build_stale_schedule`'s
    in every field it sets (review n1: the policy too, so a schedule
    registered by an older build is corrected on the next start)."""
    action = schedule.action
    if not isinstance(action, ScheduleActionStartWorkflow):
        return False
    intervals = schedule.spec.intervals
    return (
        action.workflow == "StaleQuoteCheckWorkflow"
        and action.task_queue == task_queue
        and action.execution_timeout == run_execution_timeout(interval)
        and schedule.policy.overlap == ScheduleOverlapPolicy.SKIP
        and schedule.policy.catchup_window == interval
        and len(intervals) == 1
        and intervals[0].every == interval
        and intervals[0].offset in (None, timedelta(0))
        and not schedule.spec.calendars
        and not schedule.spec.cron_expressions
    )


async def ensure_stale_quote_schedule(
    client: Client, *, interval: timedelta, task_queue: str
) -> ScheduleRegistration:
    schedule_id = stale_schedule_id(task_queue)
    desired = build_stale_schedule(interval=interval, task_queue=task_queue)
    handle = client.get_schedule_handle(schedule_id)

    try:
        description = await handle.describe()
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
        try:
            await client.create_schedule(schedule_id, desired)
        except ScheduleAlreadyRunningError:
            # Another worker created it between our describe and create.
            description = await handle.describe()
        else:
            logger.info(
                "Created Temporal schedule %r (every %s, task queue %r)",
                schedule_id,
                interval,
                task_queue,
            )
            return ScheduleRegistration.CREATED

    if _matches(description.schedule, interval=interval, task_queue=task_queue):
        logger.info("Temporal schedule %r already registered; unchanged", schedule_id)
        return ScheduleRegistration.UNCHANGED

    def _update(_input: ScheduleUpdateInput) -> ScheduleUpdate:
        return ScheduleUpdate(schedule=desired)

    await handle.update(_update)
    logger.info(
        "Updated Temporal schedule %r (every %s, task queue %r)",
        schedule_id,
        interval,
        task_queue,
    )
    return ScheduleRegistration.UPDATED
