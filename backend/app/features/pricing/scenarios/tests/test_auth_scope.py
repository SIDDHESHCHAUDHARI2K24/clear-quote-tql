"""Auth/scope coverage for `pricing.scenarios` routes (phase-p2 merge, H3):
real staff auth replaces CQ-013's `get_current_lo_stub` -- every route
requires a signed-in staff user (401 without the `cq_staff_session` cookie)
and 404s (never 403, matching CQ-015 Decision #11's style) when the
application/scenario isn't in that user's `scope_applications` scope: an LO
only ever sees their own, a Manager sees everyone's.
"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.pricing.engine.types import StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.service import create_scenario
from conftest import StaffSession

_SCENARIO_REQUEST = {
    "purchase_price": "300000.00",
    "down_payment_pct": "0.20",
    "strategy": "PRIMARY",
}


async def _priced_application(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    lo: User,
) -> Application:
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=lo)
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await db_session.commit()
    return application


async def _priced_scenario(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    lo: User,
) -> Scenario:
    application = await _priced_application(db_session, make_application, set_field_value, lo)
    scenario = await create_scenario(
        db_session, application.id, Decimal("300000.00"), Decimal("0.20"), StrategyType.PRIMARY
    )
    await db_session.commit()
    return scenario


async def test_post_scenario_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/applications/{application.id}/scenarios", json=_SCENARIO_REQUEST
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_get_products_401_without_cookie(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/scenarios/{uuid.uuid4()}/products")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_lo_gets_404_on_other_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await _priced_application(
        db_session, make_application, set_field_value, owner.user
    )

    await make_staff_session(role=UserRole.LO)  # a different LO -- overwrites the cookie

    response = await client.post(
        f"/api/v1/applications/{application.id}/scenarios", json=_SCENARIO_REQUEST
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_lo_gets_404_on_other_los_scenario(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    scenario = await _priced_scenario(db_session, make_application, set_field_value, owner.user)

    await make_staff_session(role=UserRole.LO)  # a different LO -- overwrites the cookie

    response = await client.get(f"/api/v1/scenarios/{scenario.id}/products")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_manager_gets_200_on_any_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await _priced_application(db_session, make_application, set_field_value, lo.user)

    await make_staff_session(role=UserRole.MANAGER)

    response = await client.post(
        f"/api/v1/applications/{application.id}/scenarios", json=_SCENARIO_REQUEST
    )

    assert response.status_code == 200


async def test_manager_gets_200_on_any_los_scenario(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    scenario = await _priced_scenario(db_session, make_application, set_field_value, lo.user)

    await make_staff_session(role=UserRole.MANAGER)

    response = await client.get(f"/api/v1/scenarios/{scenario.id}/products")

    assert response.status_code == 200


async def test_owner_lo_gets_200_on_own_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await _priced_application(db_session, make_application, set_field_value, lo.user)

    response = await client.post(
        f"/api/v1/applications/{application.id}/scenarios", json=_SCENARIO_REQUEST
    )

    assert response.status_code == 200
