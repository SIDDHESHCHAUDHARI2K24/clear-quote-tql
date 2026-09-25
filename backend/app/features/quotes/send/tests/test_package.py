"""CQ-019 AC1 + AC6 (API side): the default draft package and its edits."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.quotes.builder.tests.test_router import _cards, _scenarios, _seed
from app.features.quotes.send.models import QuotePackage
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]


async def _package(client: AsyncClient, application_id: uuid.UUID) -> dict[str, Any]:
    response = await client.get(f"/api/v1/applications/{application_id}/package")
    assert response.status_code == 200, response.text
    return response.json()


async def test_default_package_draft(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC1: Marcus Hale's first GET creates the default draft: the first
    group's Par (no recommendation yet) first, then at most 2 alternatives
    in group order; the recommendation text names down payment, pricing
    type and rate."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]

    scenarios = await _scenarios(client, application_id)
    cards = _cards(scenarios)
    package = await _package(client, application_id)

    first_par = scenarios["groups"][0]["quotes"][0]
    assert first_par["label"] == "Par"
    assert package["recommended_quote_id"] == first_par["id"]
    assert package["quote_ids"][0] == first_par["id"]
    assert len(package["quote_ids"]) == 3
    assert package["quote_ids"] == [c["id"] for c in cards][:3]

    group = scenarios["groups"][0]
    down = group["inputs"]["down_payment_pct"]
    text = package["recommendation_text"]
    assert text.startswith(f"{int(float(down) * 100)}% down · Par pricing at ")
    assert f"{first_par['rate_pct']}%" in text
    assert "5-year prepay" in text
    assert package["recipient_email"]
    assert package["attachments"] == ["Pre-approval letter (PDF)"]

    # A second GET returns the same package; no duplicate is created.
    again = await _package(client, application_id)
    assert again["id"] == package["id"]
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(QuotePackage)
            .where(QuotePackage.application_id == application_id)
        )
    ).scalar_one()
    assert count == 1


async def test_default_draft_puts_the_recommended_quote_first(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    cards = _cards(await _scenarios(client, application_id))
    starred = cards[-1]
    response = await client.post(f"/api/v1/quotes/{starred['id']}/recommend")
    assert response.status_code == 200, response.text

    package = await _package(client, application_id)
    assert package["quote_ids"][0] == starred["id"]
    assert package["recommended_quote_id"] == starred["id"]
    assert len(package["quote_ids"]) == 3
    assert "Buydown pricing" in package["recommendation_text"]


async def test_put_package_persists_and_redrafts_recommendation(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC6 (API): remove a quote, change the recommendation, edit the note."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    package = await _package(client, application_id)
    buydown = package["quote_ids"][1]

    body = {
        "quote_ids": [buydown, package["quote_ids"][0]],
        "recommended_quote_id": buydown,
        "lo_note": "Happy to walk you through the buydown.",
    }
    response = await client.put(f"/api/v1/applications/{application_id}/package", json=body)
    assert response.status_code == 200, response.text

    reloaded = await _package(client, application_id)
    assert reloaded["quote_ids"] == body["quote_ids"]
    assert reloaded["recommended_quote_id"] == buydown
    assert reloaded["lo_note"] == body["lo_note"]
    assert "Buydown pricing" in reloaded["recommendation_text"]

    # One recommendation per application: the builder's star follows.
    application = await db_session.get(Application, application_id, populate_existing=True)
    assert application is not None
    assert str(application.recommended_quote_id) == buydown


async def test_put_package_validation(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale", "grace_kim")
    await make_staff_session(role=UserRole.MANAGER)
    marcus = ids["marcus_hale"]
    package = await _package(client, marcus)
    grace_quote = (await _package(client, ids["grace_kim"]))["quote_ids"][0]
    url = f"/api/v1/applications/{marcus}/package"
    ours = package["quote_ids"]

    cases: list[dict[str, Any]] = [
        {"quote_ids": [ours[0], grace_quote], "recommended_quote_id": ours[0]},
        {"quote_ids": [ours[0]], "recommended_quote_id": ours[1]},
        {"quote_ids": [ours[0], ours[0]], "recommended_quote_id": ours[0]},
        {"quote_ids": ours, "recommended_quote_id": ours[0], "lo_note": "x" * 501},
        {"quote_ids": [*ours, str(uuid.uuid4())], "recommended_quote_id": ours[0]},
    ]
    for body in cases:
        response = await client.put(url, json=body)
        assert response.status_code == 422, (body, response.text)
    assert (await _package(client, marcus))["quote_ids"] == ours


async def test_package_routes_404_out_of_scope(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    package = await _package(client, ids["marcus_hale"])

    await make_staff_session(role=UserRole.LO)  # another LO
    assert (
        await client.get(f"/api/v1/applications/{ids['marcus_hale']}/package")
    ).status_code == 404
    for suffix in ("readiness", "report", "letter.html"):
        response = await client.get(f"/api/v1/packages/{package['id']}/{suffix}")
        assert response.status_code == 404, suffix
    response = await client.put(
        f"/api/v1/applications/{ids['marcus_hale']}/package",
        json={"quote_ids": [], "recommended_quote_id": None},
    )
    assert response.status_code == 404
