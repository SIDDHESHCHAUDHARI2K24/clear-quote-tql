"""`GET /applications/{id}/matches`: LO auth (401 without a session, 404 --
never 403 -- for an out-of-scope application, Decision #11 / plan.md D6) and
AC3 (a specific-address application has no matches)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import PropertyAddressStatus
from conftest import StaffSession


async def test_matches_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application()
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/matches")

    assert response.status_code == 401


async def test_matches_404_out_of_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO
    response = await client.get(f"/api/v1/applications/{application.id}/matches")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_no_matches_with_address(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC3: a specific-address application (Priya Nair's shape) gets an
    empty matches list, not an error -- the section is simply absent."""
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(
        lo=owner.user,
        occupancy=Occupancy.PRIMARY,
        strategy=None,
        address_status=PropertyAddressStatus.SPECIFIC_ADDRESS,
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/matches")

    assert response.status_code == 200
    assert response.json() == {"matches": []}


async def test_matches_empty_with_no_scenario_priced(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """A TBD application with nothing priced yet has no recommended quote to
    run matches against -- empty, not an error."""
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(
        lo=owner.user,
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["FL"],
        buy_box_metros=["Davenport"],
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/matches")

    assert response.status_code == 200
    assert response.json() == {"matches": []}
