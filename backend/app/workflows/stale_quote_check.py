"""CQ-030 `StaleQuoteCheckWorkflow` and its two activities.

The Temporal Schedule `stale-quote-check` (`stale_schedule.py`) starts this
workflow on an interval. `now` is injected (spec.md): the workflow takes an
optional `now_iso`; when the schedule starts it without one, the tiny
`resolve_clock_now` activity reads `core/clock.now()` in the worker process
(honouring `CLOCK_NOW`, E2) and hands the value to `mark_stale_activity`,
which never reads the clock itself (plan.md decision #8).
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.core import clock
    from app.features.quotes.stale.schemas import StaleResult
    from app.features.quotes.stale.service import mark_stale
    from app.workflows import db as workflow_db
    from app.workflows.retry_policies import ACTIVITY_TIMEOUT, NON_RETRYABLE_ERROR_TYPES

# Review M2: bounded like `IMPORT_ENRICH_RETRY_POLICY`. A run that keeps
# failing gives up after three attempts; the schedule's next tick retries
# the (idempotent) job anyway.
STALE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
    non_retryable_error_types=NON_RETRYABLE_ERROR_TYPES,
)


@activity.defn
async def resolve_clock_now() -> str:
    """`core/clock.now()` as ISO-8601 -- the only place the stale job reads
    the clock, and only when the caller did not inject `now`."""
    return clock.now().isoformat()


@activity.defn
async def mark_stale_activity(now_iso: str) -> StaleResult:
    """Runs `quotes.stale.service.mark_stale` at the injected `now` in its
    own session and commits."""
    now = clock.parse_instant(now_iso)
    async with workflow_db.session_factory() as db:
        result = await mark_stale(db, now)
        await db.commit()
    return result


@workflow.defn
class StaleQuoteCheckWorkflow:
    @workflow.run
    async def run(self, now_iso: str | None = None) -> StaleResult:
        if now_iso is None:
            now_iso = await workflow.execute_activity(
                resolve_clock_now,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=STALE_RETRY_POLICY,
            )
        return await workflow.execute_activity(
            mark_stale_activity,
            now_iso,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=STALE_RETRY_POLICY,
        )
