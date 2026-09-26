"""CQ-029 AC4: forcing `PricingClient` to fail (the admin Integration
panel's toggle, `integrations/common/failure_toggle.set_forced_failure`)
and re-pricing moves the application to `needs_attention` with the named
error; turning the toggle back off and resuming (`pipeline/resume`'s
signal, the same "park, then `resume`" contract `test_resume_signal.py`
covers) succeeds -- the live-demo path AC4 describes.

Lives in `backend/app/workflows/tests/` (not under `features/admin/`)
because it needs the real `ApplicationPipelineWorkflow` against the
Temporal test environment, and that harness (`temporal_worker`,
`temporal_client`, `make_persona_application`, `seed_*`, `wait_for_status`)
is local to this package's `conftest.py`. CQ-029's owned files don't cover
`backend/app/workflows/tests/`, but this is additive (a new test file, no
edits to any file another P5/P6 item owns) -- logged in plan.md as a small,
necessary exception per the agent loop's "edit anything else only for a
small necessity, and log it" rule.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core.enums import ApplicationStatus, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.integrations.common.failure_toggle import set_forced_failure
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def test_forced_pricing_failure_then_recovery(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_str_revenue: Callable[..., Awaitable[None]],
    temporal_client: Client,
    db_session: AsyncSession,
    db_lock: asyncio.Lock,
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.STR,
        requested_price=Decimal("400000.00"),
        state="FL",
        county="Hillsborough",
        zip_code="33602",
    )
    await seed_tax_rate(state="FL", county="Hillsborough")
    await seed_dscr_curve_all_buckets()
    await seed_str_revenue(zip_code="33602", beds=1)

    await set_forced_failure("pricing", True)

    workflow_id = application_workflow_id(str(application.id))
    handle = await temporal_client.start_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=workflow_id,
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    status = await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})
    assert status is ApplicationStatus.NEEDS_ATTENTION

    # Minor 7 (review round 1): this connection is shared with the
    # per-test worker's activity sessions (`conftest.py`'s
    # `activities_session_factory`), so a direct `db_session` read here
    # must hold `db_lock` too, or it can race an activity mid-flight into
    # asyncpg's "another operation is in progress" flake.
    async with db_lock:
        blocked_event = (
            (
                await db_session.execute(
                    select(ActivityEvent)
                    .where(
                        ActivityEvent.application_id == application.id,
                        ActivityEvent.type == "pipeline.pricing_blocked",
                    )
                    .order_by(ActivityEvent.at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
    assert blocked_event is not None
    assert isinstance(blocked_event.payload, dict)
    assert blocked_event.payload["message"] == "Cannot price: pricing unavailable"

    # Admin flips the Integration panel toggle back off, then the LO
    # (or the panel's own re-price hook) resumes the parked workflow --
    # exactly `POST .../pipeline/resume`'s signal (applications/router.py).
    await set_forced_failure("pricing", False)
    await handle.signal(ApplicationPipelineWorkflow.resume)
    result = await handle.result()

    assert result == "priced"

    async with db_lock:
        await db_session.refresh(application)
    assert application.status == ApplicationStatus.PRICED
