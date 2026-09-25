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
from app.features.pricing.enrichment import service as enrichment_service
from app.features.pricing.scenarios.ob_request import ObRequestOverrides
from app.features.pricing.scenarios.ob_request import (
    build_ob_search_request as real_build_ob_search_request,
)
from app.integrations.pricing.schemas import PricingRequestDTO
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def _event_types(db_session: AsyncSession, application_id: uuid.UUID) -> list[str]:
    rows = (
        (
            await db_session.execute(
                select(ActivityEvent.type)
                .where(ActivityEvent.application_id == application_id)
                .order_by(ActivityEvent.created_at)
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
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    temporal_client: Client,
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("250000.00"),
        state="OH",
        county="Franklin",
        zip_code="43215",
    )
    await seed_tax_rate(state="OH", county="Franklin")
    await seed_market_rent(zip_code="43215", beds=1)

    # plan.md #4: `applications.occupancy` is NOT NULL and CQ-013's
    # `build_ob_search_request` always derives OB's `Occupancy` as a
    # literal string, never `None` -- so Aisha's "occupancy_type null in
    # LOS" defect is reproduced by nulling *only her* request's `Occupancy`
    # after the real function builds it, leaving every other application id
    # untouched.
    async def _patched_build_request(
        db: AsyncSession,
        application_id: uuid.UUID,
        overrides: ObRequestOverrides | None = None,
    ) -> PricingRequestDTO:
        request = await real_build_ob_search_request(db, application_id, overrides)
        if application_id == application.id:
            request = request.model_copy(update={"Occupancy": None})
        return request

    monkeypatch.setattr(enrichment_service, "build_ob_search_request", _patched_build_request)

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
