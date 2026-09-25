"""P5/P6 foundation (phase-p5-p6-plan.md E14): a `source = portal`
application (CQ-032's apply wizard) already holds its parties, housing,
employment, liabilities, assets and property locally, so the pipeline
skips `import_application` and still reaches `priced` -- without ever
calling the LOS adapter.

The local data is produced here the same way the LOS import would have
written it (running the real `import_from_los` once, up front, outside the
workflow), then the LOS record is deleted and the application is flipped
to `portal`: if the workflow tried to import, there would be nothing to
import and the run would fail.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core.enums import ApplicationSource, ApplicationStatus, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.service import import_from_los
from app.features.applications.timeline.models import ActivityEvent
from app.integrations.common.models import IntegrationCall
from app.integrations.los.models import ProviderLosRecord
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id
from app.workflows.tests.conftest import install_import_from_los

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def _los_call_count(db: AsyncSession) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(IntegrationCall)
            .where(IntegrationCall.adapter == "los")
        )
    ).scalar_one()


async def test_portal_application_skips_import_and_reaches_priced(
    monkeypatch: pytest.MonkeyPatch,
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

    # Local data, as the portal submit (CQ-032) would have written it.
    await import_from_los(application.id, db_session)
    loan_number = application.los_loan_guid
    await db_session.execute(
        delete(ProviderLosRecord).where(ProviderLosRecord.loan_number == loan_number)
    )
    application.source = ApplicationSource.PORTAL
    application.los_loan_guid = None
    application.status = ApplicationStatus.INTAKE
    await db_session.commit()

    import_calls: list[uuid.UUID] = []

    async def _spy_import(application_id: uuid.UUID, db: AsyncSession) -> object:
        import_calls.append(application_id)
        raise AssertionError("import_from_los must not run for a portal application")

    install_import_from_los(monkeypatch, _spy_import)
    los_calls_before = await _los_call_count(db_session)

    result = await temporal_client.execute_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=application_workflow_id(str(application.id)),
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    assert result == "priced"
    assert import_calls == []
    assert await _los_call_count(db_session) == los_calls_before

    status = (
        await db_session.execute(select(Application.status).where(Application.id == application.id))
    ).scalar_one()
    assert status is ApplicationStatus.PRICED

    event_types = (
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
    assert "pipeline.imported" not in event_types
    assert event_types[0] == "pipeline.verified"
    assert event_types[-1] == "pipeline.priced"


async def test_los_application_still_imports(
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
    assert application.source is ApplicationSource.LOS
    await seed_tax_rate(state="FL", county="Hillsborough")
    await seed_dscr_curve_all_buckets()
    await seed_str_revenue(zip_code="33602", beds=1)

    result = await temporal_client.execute_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=application_workflow_id(str(application.id)),
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    assert result == "priced"
    first_event = (
        await db_session.execute(
            select(ActivityEvent.type)
            .where(ActivityEvent.application_id == application.id)
            .order_by(ActivityEvent.at)
            .limit(1)
        )
    ).scalar_one()
    assert first_event == "pipeline.imported"
