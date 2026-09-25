"""CQ-020 carries two PR #22 review minors (plan.md Decisions 4 and 5)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _cards, _scenarios, _seed
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]


async def _package(client: AsyncClient, application_id: uuid.UUID) -> dict[str, Any]:
    response = await client.get(f"/api/v1/applications/{application_id}/package")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_reprice_reports_moved_recommendation_as_not_cleared(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """Decision 5: when the reprice deletes the recommended leftover quote
    and the draft hands the recommendation to the next quote, the
    recommendation *moved* -- `recommendation_cleared` is False."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][0]
    par = group["quotes"][0]
    duplicate = Quote(
        scenario_id=uuid.UUID(group["id"]),
        investor=par["investor"],
        product=par["product"],
        rate=Decimal(par["rate_pct"]),
        points=Decimal("0"),
        lock_days=par["lock_days"],
        computed=par["computed"],
        label="Par",
        priced_at=datetime.now(UTC),
        created_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    db_session.add(duplicate)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={
            "quote_ids": [str(duplicate.id), par["id"]],
            "recommended_quote_id": str(duplicate.id),
        },
    )
    assert response.status_code == 200, response.text

    response = await client.post(f"/api/v1/applications/{application_id}/reprice")
    assert response.status_code == 200, response.text
    payload: Any = (
        await db_session.execute(
            select(ActivityEvent.payload).where(
                ActivityEvent.application_id == application_id,
                ActivityEvent.type == "quotes.repriced",
            )
        )
    ).scalar_one()
    assert isinstance(payload, dict)
    assert payload["deleted_quote_ids"] == [str(duplicate.id)]
    assert payload["recommendation_cleared"] is False
    application = await db_session.get(Application, application_id, populate_existing=True)
    assert application is not None
    assert str(application.recommended_quote_id) == par["id"]


async def test_untouched_draft_refills_after_builder_deletes_all_quotes(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """Decision 4: a draft the LO never saved follows the defaults -- once
    the Builder deletes every quote and new ones are priced, the next GET
    refills it."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    before = await _package(client, application_id)
    assert before["quote_ids"]

    scenarios = await _scenarios(client, application_id)
    for card in _cards(scenarios):
        response = await client.delete(f"/api/v1/quotes/{card['id']}")
        assert response.status_code == 204, response.text
    emptied = await _package(client, application_id)
    assert emptied["quote_ids"] == []

    response = await client.post(f"/api/v1/scenarios/{scenarios['groups'][0]['id']}/autoquote")
    assert response.status_code == 200, response.text
    refilled = await _package(client, application_id)
    assert refilled["id"] == before["id"]
    assert refilled["quote_ids"]
    assert refilled["recommended_quote_id"] == refilled["quote_ids"][0]
