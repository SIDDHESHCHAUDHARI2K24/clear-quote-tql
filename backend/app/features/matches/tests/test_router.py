"""`GET /applications/{id}/matches`: LO auth (401 without a session, 404 --
never 403 -- for an out-of-scope application, Decision #11 / plan.md D6),
AC3 (a specific-address application has no matches), and a happy-path
check that the endpoint actually returns real, engine-priced matches for a
TBD LTR persona (not just the empty-list edge cases below)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from seed.loader import seed_providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import PropertyAddressStatus
from app.features.pricing.scenarios.service import auto_price
from conftest import StaffSession

from .conftest import seed_dscr_rate_sheet


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


async def test_matches_happy_path_tbd_ltr(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """AC1: a real, engine-priced matches list comes back over the actual
    `GET /applications/{id}/matches` route (not just `compute_matches_for_
    package` called directly, as `test_service.py::test_matches_kathleen`
    does) -- a Kathleen-McReynolds-shaped TBD LTR persona."""
    await seed_providers(db_session)
    await db_session.commit()

    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(
        lo=owner.user,
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000.00"),
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["FL"],
        buy_box_metros=["Davenport", "Orlando"],
        recommend_matches=True,
    )
    await set_field_value(application.id, "representative_fico", Decimal("720"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0089"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2250.00"))
    seed_dscr_rate_sheet(db_session, "ONE_TO_1_25", Decimal("7.250"))
    await db_session.commit()

    await auto_price(db_session, application.id)

    response = await client.get(f"/api/v1/applications/{application.id}/matches")

    assert response.status_code == 200
    body = response.json()
    matches = body["matches"]
    assert len(matches) == 3
    for match in matches:
        price = Decimal(str(match["price"]))
        assert Decimal("210000.00") <= price <= Decimal("300000.00")
        assert match["rent_label"] == "Market rent (LTR)"
        assert match["monthly_cashflow"] is not None
        assert match["total_monthly_payment"] is not None
        assert match["cash_to_close"] is not None


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
