"""AC4: sending `resume` to a workflow parked at `needs_attention` (Ben
Ford's fixture, housing fixed) re-enters at `verify_application` and
reaches `priced` without re-running `import_application` a second time.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core.enums import ApplicationStatus, Occupancy
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import Application
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id
from app.workflows.tests.conftest import _fake_import_from_los, install_import_from_los

pytestmark = pytest.mark.usefixtures("temporal_worker")


async def test_resume_reprices_ben_ford_without_reimporting(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    make_persona_application: Callable[..., Awaitable[Application]],
    seed_tax_rate: Callable[..., Awaitable[None]],
    seed_conventional_curve: Callable[..., Awaitable[None]],
    temporal_client: Client,
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    application = await make_persona_application(
        occupancy=Occupancy.PRIMARY,
        requested_price=Decimal("200000.00"),
        state="IN",
        county="Allen",
        zip_code="46802",
        housing_rows=[(1, 2)],  # 14 months -- fails housing_history_24mo
    )
    await seed_tax_rate(state="IN", county="Allen")
    await seed_conventional_curve()

    import_call_count = 0

    async def _counting_import(application_id: uuid.UUID, db: AsyncSession) -> object:
        nonlocal import_call_count
        import_call_count += 1
        return await _fake_import_from_los(application_id, db)

    install_import_from_los(monkeypatch, _counting_import)

    workflow_id = application_workflow_id(str(application.id))
    handle = await temporal_client.start_workflow(
        ApplicationPipelineWorkflow.run,
        str(application.id),
        id=workflow_id,
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    status = await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})
    assert status is ApplicationStatus.NEEDS_ATTENTION
    assert import_call_count == 1

    # LO fixes the housing history: add a second row covering the gap.
    db_session.add(
        HousingHistory(
            application_id=application.id,
            sequence=1,
            street_address="2 Prior St",
            city="Fort Wayne",
            state="IN",
            zip="46802",
            housing_status=HousingStatus.RENT,
            residence_years=1,
            residence_months=0,
        )
    )
    await db_session.commit()

    await handle.signal(ApplicationPipelineWorkflow.resume)

    result = await handle.result()

    assert result == "priced"
    assert import_call_count == 1
