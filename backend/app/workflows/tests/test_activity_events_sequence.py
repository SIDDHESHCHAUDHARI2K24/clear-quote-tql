"""AC5: exactly one `activity_events` row per completed stage, with the
pinned `type` values, for both the Marcus Hale happy path (6 rows) and the
Aisha Coleman flagged path (import, verified, enriched, pricing_blocked).

Event-type mapping is plan.md #5's Decision: `enrich_application`,
`validate_pricing_inputs` and `auto_price_application` all reuse
`pipeline.enriched` on success (none of them change status); only `draft_
quote_set`'s success writes `pipeline.priced` (the one status flip to the
terminal value).
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
from app.features.applications.timeline.models import ActivityEvent
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def _event_types(db_session: AsyncSession, application_id: uuid.UUID) -> list[str]:
    rows = (
        (
            await db_session.execute(
                select(ActivityEvent.type)
                .where(ActivityEvent.application_id == application_id)
                # `created_at` is `server_default=func.now()`, which Postgres
                # resolves once per transaction -- every event this test's
                # single-transaction, savepoint-bound activity sessions write
                # shares the same value, so ties break on `at`, the
                # Python-side `datetime.now(UTC)` each `_write_event` call
                # actually advances (flaked under full-suite load otherwise).
                .order_by(ActivityEvent.at)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def test_marcus_hale_happy_path_writes_6_events(
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
        id=f"marcus-{uuid.uuid4()}",
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    assert result == "priced"
    assert await _event_types(db_session, application.id) == [
        "pipeline.imported",
        "pipeline.verified",
        "pipeline.enriched",
        "pipeline.enriched",
        "pipeline.enriched",
        "pipeline.priced",
    ]


async def test_aisha_coleman_flagged_path_writes_4_events(
    db_session: AsyncSession,
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    temporal_client: Client,
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    # plan.md #13 (supersedes #4): CQ-010 has merged, so persona 7's
    # "occupancy_type null in LOS" defect is reproduced for real via a LOS
    # payload with no `occupancy_type`, not a `build_ob_search_request`
    # monkeypatch.
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
        id=f"aisha-{uuid.uuid4()}",
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})

    assert await _event_types(db_session, application.id) == [
        "pipeline.imported",
        "pipeline.verified",
        "pipeline.enriched",
        "pipeline.pricing_blocked",
    ]

    blocked_row = (
        await db_session.execute(
            select(ActivityEvent).where(
                ActivityEvent.application_id == application.id,
                ActivityEvent.type == "pipeline.pricing_blocked",
            )
        )
    ).scalar_one()
    assert blocked_row.payload == {"message": "Cannot price: missing Occupancy"}
