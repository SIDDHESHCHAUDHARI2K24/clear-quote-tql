"""Auth/scope coverage for `pricing.enrichment` routes (phase-p2 merge, H3):
real staff auth replaces CQ-013's `get_current_lo_stub` -- both routes
require a signed-in staff user (401 without the `cq_staff_session` cookie)
and 404 (never 403, matching CQ-015 Decision #11's style) when the
application isn't in that user's `scope_applications` scope: an LO only
ever sees their own, a Manager sees everyone's.
"""

from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.integrations.tax.models import ProviderTaxRate
from conftest import StaffSession

_FIELD_KEY = "property_tax_annual_rate"


async def _seed_tax(db_session: AsyncSession) -> None:
    # `revert_field_value_route` re-runs `_enrich_tax`, which needs a
    # `provider_tax_rates` row for the persona's state/county (`make_
    # application`'s defaults, NC/Buncombe) to resolve -- same helper as
    # `test_field_value_override.py`'s `_seed_tax`, duplicated here rather
    # than imported since each test module owns its own fixtures.
    db_session.add(
        ProviderTaxRate(
            state="NC",
            county="Buncombe",
            annual_rate_pct=Decimal("0.6010"),
            source_name="SmartAsset",
            as_of=date(2026, 1, 1),
        )
    )
    await db_session.flush()
    await db_session.commit()


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


async def test_revert_field_value_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}/revert",
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_revert_lo_gets_404_on_other_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO -- overwrites the cookie

    response = await client.post(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}/revert",
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_revert_manager_gets_200_on_any_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await _seed_tax(db_session)
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=lo.user)
    await db_session.commit()

    patch_response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}",
        json={"value": "0.0250"},
    )
    assert patch_response.status_code == 200

    await make_staff_session(role=UserRole.MANAGER)

    response = await client.post(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}/revert",
    )

    assert response.status_code == 200


async def test_revert_owner_lo_gets_200_on_own_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await _seed_tax(db_session)
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=lo.user)
    await db_session.commit()

    patch_response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}",
        json={"value": "0.0250"},
    )
    assert patch_response.status_code == 200

    response = await client.post(
        f"/api/v1/applications/{application.id}/field-values/{_FIELD_KEY}/revert",
    )

    assert response.status_code == 200
