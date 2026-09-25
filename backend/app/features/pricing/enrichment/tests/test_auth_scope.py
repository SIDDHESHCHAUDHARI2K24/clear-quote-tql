"""Auth/scope coverage for `pricing.enrichment` routes (phase-p2 merge, H3):
real staff auth replaces CQ-013's `get_current_lo_stub` -- both routes
require a signed-in staff user (401 without the `cq_staff_session` cookie)
and 404 (never 403, matching CQ-015 Decision #11's style) when the
application isn't in that user's `scope_applications` scope: an LO only
ever sees their own, a Manager sees everyone's.
"""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from conftest import StaffSession

_FIELD_KEY = "property_tax_annual_rate"


async def test_patch_field_value_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}",
        json={"value": "0.0250"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_lo_gets_404_on_other_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO -- overwrites the cookie

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}",
        json={"value": "0.0250"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_manager_gets_200_on_any_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=lo.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.MANAGER)

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}",
        json={"value": "0.0250"},
    )

    assert response.status_code == 200


async def test_owner_lo_gets_200_on_own_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=lo.user)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}",
        json={"value": "0.0250"},
    )

    assert response.status_code == 200
