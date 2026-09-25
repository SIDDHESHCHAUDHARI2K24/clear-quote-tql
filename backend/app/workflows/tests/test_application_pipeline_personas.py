"""AC1: `ApplicationPipelineWorkflow` against each of the 10 persona
fixtures from spec.md's condensed persona table ends at the listed
"Expected workflow-terminal status", including the exact flag message for
Aisha and a housing-history flag for Ben.

Plan.md #11: literal Python fixtures per persona (not `seed/`), independent
of CQ-010 per spec.md. Plan.md #4: Aisha's "occupancy_type null in LOS"
defect is reproduced by monkeypatching `build_ob_search_request` for her
one `application_id` only — `applications.occupancy` is NOT NULL and the
real function never derives a `None` `Occupancy` otherwise.
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
from app.features.applications.property.models import PropertyAddressStatus
from app.features.applications.verification.models import Flag
from app.features.pricing.enrichment import service as enrichment_service
from app.features.pricing.scenarios.ob_request import ObRequestOverrides
from app.features.pricing.scenarios.ob_request import (
    build_ob_search_request as real_build_ob_search_request,
)
from app.integrations.pricing.schemas import PricingRequestDTO
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def _run_workflow(temporal_client: Client, application_id: uuid.UUID) -> str:
    return await temporal_client.execute_workflow(
        ApplicationPipelineWorkflow.run,
        str(application_id),
        id=application_workflow_id(str(application_id)),
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )


async def test_marcus_hale_str_tampa_fl_prices(
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

    assert await _run_workflow(temporal_client, application.id) == "priced"


async def test_kathleen_mcreynolds_ltr_tbd_property_prices(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    temporal_client: Client,
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("220000.00"),
        state="OH",
        county="Franklin",
        zip_code="43085",
        address_status=PropertyAddressStatus.TBD,
    )
    await seed_tax_rate(state="OH", county="Franklin")
    await seed_dscr_curve_all_buckets()
    await seed_market_rent(zip_code="43085", beds=1)

    assert await _run_workflow(temporal_client, application.id) == "priced"


async def test_priya_nair_primary_carmel_in_prices(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_conventional_curve: Callable[..., Awaitable[None]],
    temporal_client: Client,
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.PRIMARY,
        requested_price=Decimal("350000.00"),
        state="IN",
        county="Hamilton",
        zip_code="46032",
    )
    await seed_tax_rate(state="IN", county="Hamilton")
    await seed_conventional_curve()

    assert await _run_workflow(temporal_client, application.id) == "priced"


async def test_daniel_ortiz_primary_indianapolis_in_prices(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_conventional_curve: Callable[..., Awaitable[None]],
    temporal_client: Client,
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.PRIMARY,
        requested_price=Decimal("240000.00"),
        state="IN",
        county="Marion",
        zip_code="46201",
    )
    await seed_tax_rate(state="IN", county="Marion")
    await seed_conventional_curve()

    assert await _run_workflow(temporal_client, application.id) == "priced"


async def test_sam_reed_asheville_holdings_str_asheville_nc_prices(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_str_revenue: Callable[..., Awaitable[None]],
    temporal_client: Client,
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.STR,
        requested_price=Decimal("410000.00"),
        state="NC",
        county="Buncombe",
        zip_code="28803",
    )
    await seed_tax_rate(state="NC", county="Buncombe")
    await seed_dscr_curve_all_buckets()
    await seed_str_revenue(zip_code="28803", beds=1)

    assert await _run_workflow(temporal_client, application.id) == "priced"


async def test_tom_and_lisa_brandt_ltr_cleveland_oh_prices(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    temporal_client: Client,
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("180000.00"),
        state="OH",
        county="Cuyahoga",
        zip_code="44113",
    )
    await seed_tax_rate(state="OH", county="Cuyahoga")
    await seed_dscr_curve_all_buckets()
    await seed_market_rent(zip_code="44113", beds=1)

    assert await _run_workflow(temporal_client, application.id) == "priced"


async def test_aisha_coleman_ltr_columbus_oh_needs_attention_missing_occupancy(
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
        id=application_workflow_id(str(application.id)),
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    status = await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})
    assert status is ApplicationStatus.NEEDS_ATTENTION

    flag = (
        await db_session.execute(
            select(Flag).where(
                Flag.application_id == application.id,
                Flag.field_key == "Occupancy",
                Flag.rule == "ob_required_field",
                Flag.resolved_at.is_(None),
            )
        )
    ).scalar_one()
    assert flag is not None


async def test_ben_ford_primary_fort_wayne_in_needs_attention_housing_flag(
    db_session: AsyncSession,
    make_persona_application: Callable[..., Awaitable[Application]],
    temporal_client: Client,
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.PRIMARY,
        requested_price=Decimal("200000.00"),
        state="IN",
        county="Allen",
        zip_code="46802",
        # 14 months, single row -- "no prior address" (spec.md persona
        # table); fails `housing_history_24mo` (min 24 months required).
        housing_rows=[(1, 2)],
    )

    await temporal_client.start_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=application_workflow_id(str(application.id)),
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    status = await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})
    assert status is ApplicationStatus.NEEDS_ATTENTION

    flag = (
        await db_session.execute(
            select(Flag).where(
                Flag.application_id == application.id,
                Flag.rule == "housing_history_24mo",
                Flag.resolved_at.is_(None),
            )
        )
    ).scalar_one()
    assert flag.field_key == "current_residence_years"


async def test_grace_kim_ltr_denver_co_prices(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    temporal_client: Client,
) -> None:
    """CQ-010 advances this persona to `sent` afterward, outside this
    workflow (spec.md) — this test only asserts the workflow's own terminal
    status, `priced`."""
    application = await make_persona_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000.00"),
        state="CO",
        county="Denver",
        zip_code="80202",
    )
    await seed_tax_rate(state="CO", county="Denver")
    await seed_dscr_curve_all_buckets()
    await seed_market_rent(zip_code="80202", beds=1)

    assert await _run_workflow(temporal_client, application.id) == "priced"


async def test_luis_romero_str_scottsdale_az_prices(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_str_revenue: Callable[..., Awaitable[None]],
    temporal_client: Client,
) -> None:
    """CQ-010 advances this persona to `option_selected` afterward, outside
    this workflow (spec.md) — this test only asserts the workflow's own
    terminal status, `priced`."""
    application = await make_persona_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.STR,
        requested_price=Decimal("520000.00"),
        state="AZ",
        county="Maricopa",
        zip_code="85251",
    )
    await seed_tax_rate(state="AZ", county="Maricopa")
    await seed_dscr_curve_all_buckets()
    await seed_str_revenue(zip_code="85251", beds=1)

    assert await _run_workflow(temporal_client, application.id) == "priced"
