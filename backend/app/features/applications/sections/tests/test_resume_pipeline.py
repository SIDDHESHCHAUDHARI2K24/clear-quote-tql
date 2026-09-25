"""AC1 end to end with a real (time-skipping) Temporal environment and the
real worker: resolving Aisha Coleman's missing-occupancy flag through the
API clears the flag, resumes the pipeline, and she reaches Priced with
quotes.

The workflow fixtures (time-skipping env, real worker, activity sessions
bound to this test's connection, provider seed rows) are CQ-011's own,
imported from `app.workflows.tests.conftest` so this test runs the exact
production registration path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

from app.core.enums import ApplicationStatus, FlagSeverity, Strategy, UserRole
from app.core.errors import AppError
from app.features.applications.models import Application, ApplicationParty
from app.features.applications.sections.reverify import get_temporal_provider
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.features.pricing.enrichment.service import validate_ob_required_fields
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.workflows import worker as worker_module
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id
from app.workflows.tests import conftest as workflow_fixtures
from conftest import StaffSession

# CQ-011's workflow fixtures, re-exported so pytest finds them in this module.
activities_session_factory = workflow_fixtures.activities_session_factory
bind_activities_to_test_session = workflow_fixtures.bind_activities_to_test_session
make_persona_application = workflow_fixtures.make_persona_application
seed_dscr_curve_all_buckets = workflow_fixtures.seed_dscr_curve_all_buckets
seed_market_rent = workflow_fixtures.seed_market_rent
seed_tax_rate = workflow_fixtures.seed_tax_rate
wait_for_status = workflow_fixtures.wait_for_status


@pytest_asyncio.fixture
async def real_temporal(app: FastAPI, fake_temporal: Any) -> AsyncIterator[Client]:
    """A per-test time-skipping environment running the *real* worker
    (`worker.build_worker`), replacing the sections conftest's fake
    (depends on `fake_temporal` so this override is applied after it).
    Function-scoped on purpose: a second session-scoped worker would outlive
    this module and interfere with CQ-011's own workflow tests, which share
    the monkeypatched activity session factory."""
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        async with worker_module.build_worker(env.client):

            async def _client() -> Client:
                return env.client

            async def _provider() -> Any:
                return _client

            app.dependency_overrides[get_temporal_provider] = _provider
            yield env.client
    finally:
        await env.shutdown()


async def _quote_count(db: AsyncSession, application_id: Any) -> int:
    return (
        await db.execute(
            select(func.count(Quote.id))
            .join(Scenario, Quote.scenario_id == Scenario.id)
            .where(Scenario.application_id == application_id)
        )
    ).scalar_one()


async def _aisha_fixture(
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
) -> Application:
    application = await make_persona_application(
        occupancy=None,  # persona 7's defect: the LOS record has no occupancy_type.
        strategy=Strategy.LTR,
        requested_price=Decimal("310000.00"),
        state="OH",
        county="Franklin",
        zip_code="43215",
    )
    await seed_tax_rate(state="OH", county="Franklin")
    await seed_dscr_curve_all_buckets()
    await seed_market_rent(zip_code="43215", beds=1)
    return application


async def test_resolve_flag_resumes_pipeline(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    real_temporal: Client,
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    application = await _aisha_fixture(
        make_persona_application, seed_tax_rate, seed_dscr_curve_all_buckets, seed_market_rent
    )
    await make_staff_session(role=UserRole.MANAGER)
    handle = await real_temporal.start_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=application_workflow_id(str(application.id)),
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )
    await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})

    before = (await client.get(f"/api/v1/applications/{application.id}/sections/property")).json()
    assert [f["message"] for f in before["flags"]] == ["Cannot price: missing Occupancy"]

    response = await client.put(
        f"/api/v1/applications/{application.id}/fields/occupancy_type",
        json={"value": "investment"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["flags"] == []
    assert body["resume"] == {"requested": True, "reason": "resumed"}

    assert await handle.result() == "priced"
    status = (
        await db_session.execute(select(Application.status).where(Application.id == application.id))
    ).scalar_one()
    assert status is ApplicationStatus.PRICED
    assert await _quote_count(db_session, application.id) > 0
    types = (
        (
            await db_session.execute(
                select(ActivityEvent.type)
                .where(ActivityEvent.application_id == application.id)
                .order_by(ActivityEvent.at)
            )
        )
        .scalars()
        .all()
    )
    for expected in ("field.edited", "flag.resolved", "pipeline.resume_requested"):
        assert expected in types
    assert types.index("pipeline.resumed") > types.index("pipeline.resume_requested")
    assert types[-1] == "pipeline.priced"


async def test_resume_starts_pipeline_when_no_run(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],
    seed_market_rent: Callable[..., Awaitable[None]],
    real_temporal: Client,
) -> None:
    """A seeded application (demo-reset: no Temporal run) is imported and
    parked at needs_attention by the service functions directly. Fixing it
    starts the pipeline; the import step does not duplicate rows."""
    from app.features.applications.service import import_from_los
    from app.features.applications.verification.service import run_and_persist

    application = await _aisha_fixture(
        make_persona_application, seed_tax_rate, seed_dscr_curve_all_buckets, seed_market_rent
    )
    await import_from_los(application.id, db_session)
    await run_and_persist(application.id, db_session)
    with pytest.raises(AppError):
        await validate_ob_required_fields(db_session, application.id)
    application.status = ApplicationStatus.NEEDS_ATTENTION
    await db_session.commit()
    flag = (
        await db_session.execute(select(Flag).where(Flag.application_id == application.id))
    ).scalar_one()
    assert flag.severity is FlagSeverity.BLOCKING
    await make_staff_session(role=UserRole.MANAGER)

    body = (
        await client.put(
            f"/api/v1/applications/{application.id}/fields/occupancy_type",
            json={"value": "investment"},
        )
    ).json()

    assert body["resume"] == {"requested": True, "reason": "started"}
    handle = real_temporal.get_workflow_handle(application_workflow_id(str(application.id)))
    assert await handle.result() == "priced"
    parties = (
        await db_session.execute(
            select(func.count(ApplicationParty.id)).where(
                ApplicationParty.application_id == application.id
            )
        )
    ).scalar_one()
    assert parties == 1
    await db_session.refresh(application)
    assert application.occupancy is not None
    assert application.occupancy.value == "investment"
    assert await _quote_count(db_session, application.id) > 0
