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

Steps 2-3 run under the application row lock (review M1). Step 4 asks
Temporal (`describe`, short `rpc_timeout`) with the lock released
(lock-hardening minor 1), then takes the lock again only to re-check the
status and flags, check for a pending resume and write the
`pipeline.resume_requested` event. A signal is skipped while an earlier
resume is still pending (the last `pipeline.*` event is our own
`pipeline.resume_requested`, less than `RESUME_PENDING_TTL` old) and the
run is still running, so two quick edits send one signal and write one
event. An older pending resume is treated as lost (e.g. the API crashed
before signalling) and the signal, which is idempotent, is sent again
(minor 4). A run that closed meanwhile is restarted as usual.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.core.clock import now
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

RESUME_PENDING_TTL = timedelta(seconds=60)
"""How long a `pipeline.resume_requested` counts as pending (minor 4)."""

DESCRIBE_RPC_TIMEOUT = timedelta(seconds=3)
"""`describe` timeout: an edit must not wait long on a slow Temporal."""


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
    """True when the latest `pipeline.*` event is a resume we requested less
    than `RESUME_PENDING_TTL` ago and the pipeline has not written anything
    since (review minor 8, lock-hardening minor 4).

    Ordering (lock-hardening nit, accepted): `created_at` is the DB's
    transaction start time, so an event written by a transaction that began
    before ours but committed after it sorts first. The pipeline's verify
    waits on the lock *inside* its transaction, so its `pipeline.flagged`
    can sort before our resume and we would wrongly see "pending". That
    window ends when the TTL expires, and a fresh edit then signals again,
    so it is accepted rather than adding a `clock_timestamp()` column."""
    latest = (
        await db.execute(
            select(
                ActivityEvent.type,
                ActivityEvent.payload,
                ActivityEvent.at,
                (func.clock_timestamp() - ActivityEvent.created_at).label("db_age"),
            )
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
    if payload.get("reason") not in ("resumed", "started"):
        return False
    # Expired on either clock: the DB clock (`created_at`, unaffected by a
    # frozen or future `CLOCK_NOW`) or the app clock (`at`, stamped by
    # `events.add_event` with `clock.now()`, so a demo or test that moves
    # `CLOCK_NOW` forward expires it too).
    expired = latest.db_age >= RESUME_PENDING_TTL or now() - latest.at >= RESUME_PENDING_TTL
    return not expired


async def _plan_resume(
    client: Client, application_id: uuid.UUID
) -> tuple[ResumeReason, Callable[[], Awaitable[None]] | None]:
    """Decides how to resume without touching the DB (call it without the
    application lock): signal a running run, start one when none exists
    (seeded apps), or give up on a closed run. Returns the reason plus the
    Temporal call to make (deferred, see `ResumeOutcome.dispatch`)."""
    workflow_id = application_workflow_id(str(application_id))
    handle = client.get_workflow_handle(workflow_id)
    try:
        description = await handle.describe(rpc_timeout=DESCRIBE_RPC_TIMEOUT)
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

        async def _signal() -> None:
            await handle.signal(ApplicationPipelineWorkflow.resume)

        return "resumed", _signal
    return "workflow_closed", None


async def _not_resumable(
    db: AsyncSession, application_id: uuid.UUID, *, blocking_open: bool | None = None
) -> ResumeReason | None:
    """Why the pipeline must not be resumed now, or None. Reads the open
    flags itself unless `blocking_open` is given."""
    status = (
        await db.execute(select(Application.status).where(Application.id == application_id))
    ).scalar_one()
    if status is not ApplicationStatus.NEEDS_ATTENTION:
        return "not_needs_attention"
    if blocking_open is None:
        blocking_open = any(
            flag.severity is FlagSeverity.BLOCKING for flag in await _open_flags(db, application_id)
        )
    if blocking_open:
        return "blocking_flags_remain"
    return None


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

    blocked = await _not_resumable(db, application_id, blocking_open=blocking_open)
    # Commits the flag events and releases the lock: Temporal is asked
    # without it (lock-hardening minor 1).
    await db.commit()
    if blocked is not None:
        return ResumeOutcome(requested=False, reason=blocked)

    try:
        client = await temporal()
        reason, dispatch = await _plan_resume(client, application_id)
    except Exception:
        logger.exception("Could not resume the pipeline for %s", application_id)
        return ResumeOutcome(requested=False, reason="temporal_unavailable")

    # Under the lock again: only the re-check, the pending check and the
    # event write. The pipeline may have moved on while Temporal answered.
    await lock_application(db, application_id)
    blocked = await _not_resumable(db, application_id)
    if blocked is not None:
        await db.commit()
        return ResumeOutcome(requested=False, reason=blocked)
    if reason == "resumed" and await _resume_pending(db, application_id):
        # Our last resume is still waiting to be picked up by this run.
        await db.commit()
        return ResumeOutcome(requested=True, reason="already_requested")

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
