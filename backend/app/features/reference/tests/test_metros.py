"""`GET /reference/metros` (CQ-028 plan.md #17)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.property.models import PropertyType
from app.integrations.property_search.models import DealGrade, ProviderListing
from conftest import BorrowerSession, StaffSession


async def _seed_listing(db: AsyncSession, metro: str, state: str) -> None:
    db.add(
        ProviderListing(
            address="1 Test St",
            city=metro,
            state=state,
            zip="33602",
            county="Hillsborough",
            metro=metro,
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


async def test_metros_for_staff(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await _seed_listing(db_session, "Brandon", "FL")
    await make_staff_session(role=UserRole.LO)

    response = await client.get("/api/v1/reference/metros", params={"states": "fl,NC"})

    assert response.status_code == 200
    states = response.json()["states"]
    assert [s["state"] for s in states] == ["FL", "NC"]
    assert {"Brandon", "Orlando", "Tampa"} <= set(states[0]["metros"])
    assert states[0]["metros"] == sorted(states[0]["metros"])
    assert "Charlotte" in states[1]["metros"]


async def test_metros_for_borrower(
    client: AsyncClient, make_borrower_session: Callable[..., Awaitable[BorrowerSession]]
) -> None:
    await make_borrower_session()

    response = await client.get("/api/v1/reference/metros", params={"states": "OH"})

    assert response.status_code == 200
    assert "Columbus" in response.json()["states"][0]["metros"]


async def test_metros_requires_session(client: AsyncClient) -> None:
    response = await client.get("/api/v1/reference/metros", params={"states": "FL"})

    assert response.status_code == 401


async def test_metros_rejects_session_of_deleted_user(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    staff = await make_staff_session(role=UserRole.LO)
    await db_session.delete(staff.user)
    await db_session.flush()

    response = await client.get("/api/v1/reference/metros", params={"states": "FL"})

    assert response.status_code == 401


async def test_metros_rejects_bad_state(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    await make_staff_session(role=UserRole.LO)

    response = await client.get("/api/v1/reference/metros", params={"states": "Florida"})

    assert response.status_code == 422
