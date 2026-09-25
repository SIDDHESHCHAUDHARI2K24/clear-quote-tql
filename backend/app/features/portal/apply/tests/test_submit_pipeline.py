"""AC1 (CQ-032): a new borrower's Tampa STR wizard application reaches
Priced with default quotes and no LO action.

Runs the real submit endpoint, which starts the real
`ApplicationPipelineWorkflow` on a time-skipping Temporal test server with
the real production worker (`app.workflows.worker.build_worker`). The
workflow fixtures are re-used from `app/workflows/tests/conftest.py`
(activities share this test's DB connection; see that module).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core.enums import ApplicationStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.portal.apply import router as apply_router
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.integrations.property_search.models import ProviderListing
from app.workflows.tests.conftest import (  # noqa: F401
    activities_session_factory,
    bind_activities_to_test_session,
    seed_dscr_curve_all_buckets,
    seed_str_revenue,
    seed_tax_rate,
    temporal_client,
    temporal_env,
    temporal_worker,
    wait_for_status,
)

from .conftest import SentEmail

pytestmark = pytest.mark.usefixtures("temporal_worker")

BASE = "/api/v1/portal/applications"
Tabs = Callable[[], dict[str, dict[str, Any]]]


@pytest_asyncio.fixture
async def real_temporal(
    app: FastAPI,
    temporal_client: Client,  # noqa: F811
) -> AsyncIterator[Client]:
    async def _factory() -> Client:
        return temporal_client

    app.dependency_overrides[apply_router.temporal_client_factory] = lambda: _factory
    try:
        yield temporal_client
    finally:
        app.dependency_overrides.pop(apply_router.temporal_client_factory, None)


async def test_submitted_tampa_str_reaches_priced(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    sent_emails: list[SentEmail],
    real_temporal: Client,
    seed_tax_rate: Callable[..., Awaitable[None]],  # noqa: F811
    seed_dscr_curve_all_buckets: Callable[..., Awaitable[None]],  # noqa: F811
    seed_str_revenue: Callable[..., Awaitable[None]],  # noqa: F811
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],  # noqa: F811
) -> None:
    await seed_tax_rate(state="FL", county="Hillsborough")
    await seed_dscr_curve_all_buckets()
    await seed_str_revenue(zip_code="33602", beds=1)

    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    tabs = valid_tabs()
    for tab in ("you", "property", "income", "consent"):
        response = await client.patch(
            f"{BASE}/{draft_id}/draft", json={"tab": tab, "data": tabs[tab]}
        )
        assert response.json()["tab_valid"] is True, response.json()

    submitted = await client.post(f"{BASE}/{draft_id}/submit")
    assert submitted.status_code == 200, submitted.json()
    assert submitted.json()["pipeline_started"] is True
    app_id = uuid.UUID(submitted.json()["application_id"])

    status = await wait_for_status(
        db_session,
        app_id,
        {ApplicationStatus.PRICED, ApplicationStatus.NEEDS_ATTENTION},
        timeout=30.0,
    )
    assert status is ApplicationStatus.PRICED

    quotes = (
        await db_session.execute(
            select(func.count())
            .select_from(Quote)
            .join(Scenario, Scenario.id == Quote.scenario_id)
            .where(Scenario.application_id == app_id)
        )
    ).scalar_one()
    assert quotes > 0

    event_types = (
        (
            await db_session.execute(
                select(ActivityEvent.type)
                .where(ActivityEvent.application_id == app_id)
                .order_by(ActivityEvent.at, ActivityEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert "pipeline.imported" not in event_types
    assert "pipeline.verified" in event_types
    assert event_types[-1] == "pipeline.priced"
    # No LO action: the only non-pipeline events are the submit's own.
    assert {t for t in event_types if not t.startswith("pipeline.")} == {
        "application.submitted",
        "application.assigned",
    }
