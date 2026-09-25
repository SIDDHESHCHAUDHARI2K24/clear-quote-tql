"""Re-verify after every LO edit and resume the pipeline when the last
blocking flag clears (spec "After any edit"; plan.md Decisions #8, #9).

`reverify_and_maybe_resume`:

1. Re-runs CQ-012's rules (`run_and_persist`, commits).
2. If the application has open `ob_required_field` flags (raised by the
   pricing Validate stage, e.g. Aisha Coleman's missing Occupancy), re-runs
   `validate_ob_required_fields`, which resolves them or keeps them.
3. Writes one `flag.raised` / `flag.resolved` activity event per flag that
   changed.
4. If the application is `needs_attention` and no open `blocking` flag
   remains, signals the CQ-011 workflow's `resume`. A seeded application
   has no Temporal run (demo-reset drives the service functions directly),
   so NOT_FOUND starts the pipeline instead (same workflow id). A run
   that failed (or was terminated, cancelled or timed out) is started
   again under the same id (`ALLOW_DUPLICATE_FAILED_ONLY`).

Steps 2-4 run under the application row lock (review M1), and step 4 is
skipped while an earlier resume is still pending (the last `pipeline.*`
event is our own `pipeline.resume_requested`) and the run is still
running, so two quick edits send one signal and write one event. A run
that closed meanwhile is restarted as usual.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.core.enums import ApplicationStatus, FlagSeverity
from app.core.errors import AppError
from app.features.applications.locking import lock_application
from app.features.applications.models import Application
from app.features.applications.sections import events
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.features.applications.verification.rules import OB_REQUIRED_FIELD_RULE
from app.features.applications.verification.service import run_and_persist
from app.features.pricing.enrichment.service import validate_ob_required_fields
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.client import get_temporal_client
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id

logger = logging.getLogger(__name__)

ResumeReason = Literal[
    "resumed",
    "started",
    "already_requested",
    "not_needs_attention",
    "blocking_flags_remain",
    "workflow_closed",
    "temporal_unavailable",
]

TemporalProvider = Callable[[], Awaitable[Client]]


async def get_temporal_provider() -> TemporalProvider:
    """FastAPI dependency: hands out the *function* that connects to
    Temporal, so an edit only connects when a resume is actually needed.
    Tests override this dependency with the time-skipping env's client."""
    return get_temporal_client


@dataclass(frozen=True)
class ResumeOutcome:
    requested: bool
    reason: ResumeReason
    dispatch: Callable[[], Awaitable[None]] | None = None
    """The Temporal signal/start to send. Deferred so the caller sends it
    after its last DB read: once resumed, the pipeline's activities write
    to the same application straight away."""

    async def send(self) -> ResumeOutcome:
        """Runs `dispatch`; a Temporal failure is logged and reported as
        `temporal_unavailable` (the LO's edit is already saved)."""
        if self.dispatch is None:
            return self
        try:
            await self.dispatch()
        except Exception:
            logger.exception("Could not resume the pipeline")
            return ResumeOutcome(requested=False, reason="temporal_unavailable")
        return ResumeOutcome(requested=self.requested, reason=self.reason)


async def _open_flags(db: AsyncSession, application_id: uuid.UUID) -> list[Flag]:
    return list(
        (
            await db.execute(
                select(Flag).where(
                    Flag.application_id == application_id, Flag.resolved_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )


def _flag_payload(flag: Flag) -> dict[str, object]:
    return {
        "flag_id": str(flag.id),
        "field_key": flag.field_key,
        "rule": flag.rule,
        "severity": flag.severity.value,
        "tab": flag.tab.value,
        "message": flag.message or flag.rule,
    }


_RESTARTABLE = frozenset(
    {
        WorkflowExecutionStatus.FAILED,
        WorkflowExecutionStatus.TERMINATED,
        WorkflowExecutionStatus.CANCELED,
        WorkflowExecutionStatus.TIMED_OUT,
    }
)
"""Closed states `ALLOW_DUPLICATE_FAILED_ONLY` lets us start a new run over."""


async def _resume_pending(db: AsyncSession, application_id: uuid.UUID) -> bool:
    """True when the latest `pipeline.*` event is a resume we requested and
    the pipeline has not written anything since (review minor 8)."""
    latest = (
        await db.execute(
            select(ActivityEvent.type, ActivityEvent.payload)
            .where(
                ActivityEvent.application_id == application_id,
                ActivityEvent.type.startswith("pipeline."),
            )
            # `created_at` is the DB clock for every writer; `at` is not
            # (`CLOCK_NOW` moves ours, the worker stamps the wall clock).
            .order_by(ActivityEvent.created_at.desc(), ActivityEvent.at.desc())
            .limit(1)
        )
    ).first()
    if latest is None or latest.type != events.RESUME_REQUESTED:
        return False
    payload = latest.payload if isinstance(latest.payload, dict) else {}
    return payload.get("reason") in ("resumed", "started")


async def _plan_resume(
    client: Client, application_id: uuid.UUID, pending: bool = False
) -> tuple[ResumeReason, Callable[[], Awaitable[None]] | None]:
    """Decides how to resume without touching the DB: signal a running run,
    start one when none exists (seeded apps), or give up on a closed run.
    Returns the reason plus the Temporal call to make (deferred, see
    `ResumeOutcome.dispatch`)."""
    workflow_id = application_workflow_id(str(application_id))
    handle = client.get_workflow_handle(workflow_id)
    try:
        description = await handle.describe()
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
        description = None

    if description is None or description.status in _RESTARTABLE:

        async def _start() -> None:
            try:
                await client.start_workflow(
                    ApplicationPipelineWorkflow.run,
                    str(application_id),
                    id=workflow_id,
                    task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
                    # No run, or the last one failed: start one. A completed
                    # (priced) run is never repeated (review minor 6).
                    id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
                )
            except WorkflowAlreadyStartedError:
                logger.info("Pipeline for %s was started concurrently", application_id)

        return "started", _start
    if description.status is WorkflowExecutionStatus.RUNNING:
        if pending:
            # Our last resume is still waiting to be picked up by this run.
            return "already_requested", None

        async def _signal() -> None:
            await handle.signal(ApplicationPipelineWorkflow.resume)

        return "resumed", _signal
    return "workflow_closed", None


async def reverify_and_maybe_resume(
    db: AsyncSession,
    application_id: uuid.UUID,
    temporal: TemporalProvider,
) -> ResumeOutcome:
    """See module docstring. Commits."""
    # Plain-dict snapshots: ORM rows may be expired by the commits/rollback
    # below, and an expired attribute cannot be lazy-loaded under asyncio.
    before = {flag.id: _flag_payload(flag) for flag in await _open_flags(db, application_id)}

    await run_and_persist(application_id, db)

    # Everything below runs under the application lock (review M1). The
    # OB validator commits (releasing it), so it is taken again after.
    await lock_application(db, application_id)
    if any(f.rule == OB_REQUIRED_FIELD_RULE for f in await _open_flags(db, application_id)):
        try:
            await validate_ob_required_fields(db, application_id)
        except AppError:
            # Still missing (flags kept and committed by the validator) or
            # the request cannot be built yet; either way flags stay open.
            await db.rollback()
        await lock_application(db, application_id)

    after_flags = await _open_flags(db, application_id)
    after = {flag.id: _flag_payload(flag) for flag in after_flags}
    blocking_open = any(flag.severity is FlagSeverity.BLOCKING for flag in after_flags)
    for flag_id, payload in after.items():
        if flag_id not in before:
            events.add_event(
                db,
                application_id,
                actor=events.SYSTEM_ACTOR,
                type=events.FLAG_RAISED,
                payload=payload,
            )
    for flag_id, payload in before.items():
        if flag_id not in after:
            events.add_event(
                db,
                application_id,
                actor=events.SYSTEM_ACTOR,
                type=events.FLAG_RESOLVED,
                payload=payload,
            )

    status = (
        await db.execute(select(Application.status).where(Application.id == application_id))
    ).scalar_one()
    if status is not ApplicationStatus.NEEDS_ATTENTION:
        await db.commit()
        return ResumeOutcome(requested=False, reason="not_needs_attention")
    if blocking_open:
        await db.commit()
        return ResumeOutcome(requested=False, reason="blocking_flags_remain")
    pending = await _resume_pending(db, application_id)

    try:
        client = await temporal()
        reason, dispatch = await _plan_resume(client, application_id, pending)
    except Exception:
        logger.exception("Could not resume the pipeline for %s", application_id)
        await db.commit()
        return ResumeOutcome(requested=False, reason="temporal_unavailable")

    if reason == "already_requested":
        await db.commit()
        return ResumeOutcome(requested=True, reason=reason)

    requested = reason in ("resumed", "started")
    events.add_event(
        db,
        application_id,
        actor=events.SYSTEM_ACTOR,
        type=events.RESUME_REQUESTED,
        payload={
            "reason": reason,
            "message": (
                "All checks pass; pricing resumed"
                if requested
                else "All checks pass, but the pipeline run has already finished"
            ),
        },
    )
    await db.commit()
    return ResumeOutcome(requested=requested, reason=reason, dispatch=dispatch)
