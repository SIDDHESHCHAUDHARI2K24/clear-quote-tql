"""CQ-019 AC5: send readiness blockers."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.clients.models import Client
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _seed
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]


async def _readiness(client: AsyncClient, application_id: uuid.UUID) -> dict[str, Any]:
    package = (await client.get(f"/api/v1/applications/{application_id}/package")).json()
    response = await client.get(f"/api/v1/packages/{package['id']}/readiness")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("persona", ["grace_kim", "aisha_coleman"])
async def test_readiness_blockers(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff, persona: str
) -> None:
    ids = await _seed(db_session, persona)
    await make_staff_session(role=UserRole.MANAGER)
    readiness = await _readiness(client, ids[persona])

    assert readiness["ready"] is False
    first = readiness["blockers"][0]
    if persona == "grace_kim":
        # Sent 25 days ago: its quotes are past the 21-day rate window.
        assert first == {
            "code": "quotes_stale",
            "message": "Quotes are out of date",
            "tab": "pricing",
        }
    else:
        # Aisha Coleman: missing Occupancy is an open blocking flag.
        assert first["code"] == "open_flag"
        assert first["message"] == "Open flag: Occupancy type — required for pricing"
        assert first["tab"] == "pricing"


async def test_ready_package_has_no_blockers(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    assert await _readiness(client, ids["marcus_hale"]) == {"ready": True, "blockers": []}


async def test_readiness_stale_flag_missing_recommendation_and_email(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)
    package = (await client.get(f"/api/v1/applications/{application_id}/package")).json()

    await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={"quote_ids": package["quote_ids"], "recommended_quote_id": None},
    )
    await db_session.execute(
        update(Quote).where(Quote.id == package["quote_ids"][1]).values(stale=True)
    )
    application = await db_session.get(Application, application_id)
    assert application is not None
    await db_session.execute(
        update(Client).where(Client.id == application.client_id).values(email="")
    )
    await db_session.commit()

    codes = [b["code"] for b in (await _readiness(client, application_id))["blockers"]]
    assert codes == ["quotes_stale", "no_recommended_quote", "borrower_email_missing"]


async def test_manual_quote_no_longer_offered_blocks(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """CQ-018 follow-up: a Manual quote left stale by a reprice (its product
    left the grid) is named in readiness."""
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)
    package = (await client.get(f"/api/v1/applications/{application_id}/package")).json()
    par = await db_session.get(Quote, uuid.UUID(package["quote_ids"][0]))
    assert par is not None
    manual = Quote(
        scenario_id=par.scenario_id,
        investor=par.investor,
        product="Retired Product",
        rate=par.rate,
        points=par.points,
        lock_days=par.lock_days,
        computed=par.computed,
        label="Manual",
        priced_at=par.priced_at - timedelta(hours=1),
        stale=True,
    )
    db_session.add(manual)
    await db_session.commit()
    response = await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={"quote_ids": [str(par.id), str(manual.id)], "recommended_quote_id": str(par.id)},
    )
    assert response.status_code == 200, response.text

    blockers = (await _readiness(client, application_id))["blockers"]
    assert blockers[0]["code"] == "quotes_stale"
    assert blockers[1] == {
        "code": "quote_not_offered",
        "message": "1 manual quote is no longer offered — delete or re-pick",
        "tab": "pricing",
    }
