"""Property actions, buy-box metros (AC6) and document receipt."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.assets.models import Document
from app.features.applications.models import Application
from app.features.applications.property.models import PropertyAddressStatus, PropertyType
from app.features.applications.timeline.models import ActivityEvent
from app.integrations.property_search.models import DealGrade, ProviderListing

MakeApp = Callable[..., Awaitable[Application]]


async def _listing(db: AsyncSession, *, city: str, state: str, zip_code: str, county: str) -> None:
    db.add(
        ProviderListing(
            address=f"{uuid.uuid4().hex[:6]} Test St",
            city=city,
            state=state,
            zip=zip_code,
            county=county,
            metro=city,
            list_price=Decimal("250000.00"),
            beds=3,
            baths=Decimal("2.0"),
            sqft=1500,
            property_type=PropertyType.SINGLE_FAMILY,
            image_url="https://example.test/x.jpg",
            deal_grade=DealGrade.GOOD_BUY,
        )
    )
    await db.commit()


async def test_buy_box_metros(client: AsyncClient, make_app: MakeApp) -> None:
    """AC6: picking FL, then Tampa and Orlando, stores both metros."""
    app = await make_app(address_status=PropertyAddressStatus.TBD, state="IN")
    url = f"/api/v1/applications/{app.id}/property"

    body = (
        await client.patch(
            url, json={"buy_box_states": ["fl"], "buy_box_metros": ["Tampa", "Orlando"]}
        )
    ).json()

    assert body["property"]["buy_box_states"] == ["FL"]
    assert body["property"]["buy_box_metros"] == ["Tampa", "Orlando"]

    bad = await client.patch(url, json={"buy_box_metros": ["Atlanta"]})
    assert bad.status_code == 422

    # Switching states drops metros that are not in the new states.
    body = (await client.patch(url, json={"buy_box_states": ["NC"]})).json()
    assert body["property"]["buy_box_metros"] == []


async def test_property_tbd_toggle(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    """AC6: TBD -> address turns recommend-matches off and removes TBD;
    the county comes from the zip lookup."""
    await _listing(db_session, city="Davenport", state="FL", zip_code="33896", county="Polk")
    app = await make_app(address_status=PropertyAddressStatus.TBD, state="FL")
    url = f"/api/v1/applications/{app.id}/property"

    body = (
        await client.patch(
            url,
            json={
                "address": {
                    "street_address": "12 Palm Way",
                    "city": "Davenport",
                    "state": "FL",
                    "zip": "33896",
                }
            },
        )
    ).json()

    assert body["property"]["tbd"] is False
    assert body["property"]["recommend_matches"] is False
    fields = {f["field_key"]: f for r in body["records"] for f in r["fields"]}
    assert fields["property.county"]["value"] == "Polk"
    assert fields["property.street_address"]["value"] == "12 Palm Way"
    assert fields["property.street_address"]["source"] == "lo_entry"
    await db_session.refresh(app)
    assert app.subject_state == "FL"

    body = (await client.patch(url, json={"tbd": True})).json()
    assert body["property"]["tbd"] is True
    assert body["property"]["recommend_matches"] is True

    body = (await client.patch(url, json={"recommend_matches": False})).json()
    assert body["property"]["recommend_matches"] is False

    assert (await client.patch(url, json={"tbd": False})).status_code == 422
    types = (
        (
            await db_session.execute(
                select(ActivityEvent.type).where(ActivityEvent.application_id == app.id)
            )
        )
        .scalars()
        .all()
    )
    assert types.count("property.updated") == 3


async def test_mark_document_received(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app()
    other = await make_app()
    doc = Document(application_id=app.id, doc_type="pay_stub", object_key="k/pay_stub.pdf")
    foreign = Document(application_id=other.id, doc_type="w2", object_key="k/w2.pdf")
    db_session.add_all([doc, foreign])
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/applications/{app.id}/documents/{doc.id}", json={"received": True}
    )

    assert response.status_code == 200
    [item] = response.json()["assets"]["documents"]
    assert item["doc_type"] == "pay_stub"
    assert item["received"] is True
    assert item["received_at"] is not None
    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == app.id,
                    ActivityEvent.type == "document.received",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert (
        await client.patch(
            f"/api/v1/applications/{app.id}/documents/{foreign.id}", json={"received": True}
        )
    ).status_code == 404
