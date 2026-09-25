"""CQ-016 D7: `applications.last_pipeline_stage` tracks the running pipeline
activity, and lands on a terminal `ApplicationStatus` value
(`priced`/`needs_attention`) once the chain stops or finishes -- reusing the
same two personas/fixtures as `test_activity_events_sequence.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core.enums import ApplicationStatus, Occupancy, Strategy
from app.features.applications.models import Application
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, is_pipeline_stage_terminal

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def _stage(db_session: AsyncSession, application_id: uuid.UUID) -> str | None:
    # Core column select (like `_wait_for_status`): bypasses the ORM
    # identity map so it always sees the latest value committed by sibling
    # activity sessions on the same connection.
    return (
        await db_session.execute(
            select(Application.last_pipeline_stage).where(Application.id == application_id)
        )
    ).scalar_one()


async def test_marcus_hale_happy_path_lands_on_priced(
    db_session: AsyncSession,
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_str_revenue: Callable[..., Awaitable[None]],
    temporal_client: Client,
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

    result = await temporal_client.execute_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=f"marcus-stage-{uuid.uuid4()}",
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    assert result == "priced"
    stage = await _stage(db_session, application.id)
    assert stage == ApplicationStatus.PRICED.value
    assert is_pipeline_stage_terminal(stage)


async def test_aisha_coleman_flagged_path_lands_on_needs_attention(
    db_session: AsyncSession,
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    temporal_client: Client,
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    application = await make_persona_application(
        occupancy=None,
        strategy=Strategy.LTR,
        requested_price=Decimal("250000.00"),
        state="OH",
        county="Franklin",
        zip_code="43215",
    )
    await seed_tax_rate(state="OH", county="Franklin")
    await seed_market_rent(zip_code="43215", beds=1)

    await temporal_client.start_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=f"aisha-stage-{uuid.uuid4()}",
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})

    stage = await _stage(db_session, application.id)
    assert stage == ApplicationStatus.NEEDS_ATTENTION.value
    assert is_pipeline_stage_terminal(stage)


def test_is_pipeline_stage_terminal_running_names_are_not_terminal() -> None:
    from app.workflows.constants import PipelineStage

    for stage in PipelineStage:
        assert not is_pipeline_stage_terminal(stage.value)
    assert is_pipeline_stage_terminal(None)
