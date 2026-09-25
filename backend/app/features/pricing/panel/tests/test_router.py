"""`GET /applications/{id}/pricing` route: auth/scope (matches the other
`application_id`-keyed pricing routes' 401/404 shape) and AC1's golden
values for Marcus Hale, seeded through the real pipeline.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FieldSource, Occupancy, UserRole
from app.features.applications.models import Application
from app.features.applications.verification.models import FieldValue
from app.features.pricing.engine.types import StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from conftest import StaffSession


async def test_get_pricing_requires_staff_auth(
    client: AsyncClient,
    make_application: Callable[..., Awaitable[Application]],
    db_session: AsyncSession,
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/pricing")
    assert response.status_code == 401


async def test_get_pricing_404_for_other_los_application(
    client: AsyncClient,
    make_application: Callable[..., Awaitable[Application]],
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO
    response = await client.get(f"/api/v1/applications/{application.id}/pricing")
    assert response.status_code == 404


async def test_get_pricing_200_for_owning_lo(
    client: AsyncClient,
    make_application: Callable[..., Awaitable[Application]],
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/pricing")
    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == str(application.id)
    assert body["breakdown"] is None  # not priced yet
    assert body["has_stale_quotes"] is False


async def test_override_property_tax_recomputes_breakdown_immediately(
    client: AsyncClient,
    make_application: Callable[..., Awaitable[Application]],
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
    make_scenario: Callable[..., Awaitable[Scenario]],
    make_quote: Callable[..., Awaitable[Quote]],
) -> None:
    """AC3: overriding property tax shows "LO override" and recomputes the
    total -- proven here against the live `GET .../pricing` breakdown, not
    just the `field_values` row (the stale-marking side of AC3 is covered
    by `pricing/enrichment/tests/test_stale_marking.py`)."""
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    await db_session.commit()

    db_session.add(
        FieldValue(
            application_id=application.id,
            field_key="representative_fico",
            value="740",
            source=FieldSource.CREDIT_BUREAU,
        )
    )
    db_session.add(
        FieldValue(
            application_id=application.id,
            field_key="property_tax_annual_rate",
            value="0.012",
            source=FieldSource.SMARTASSET,
        )
    )
    db_session.add(
        FieldValue(
            application_id=application.id,
            field_key="homeowners_ins_annual",
            value="1800.00",
            source=FieldSource.STEADILY,
        )
    )
    db_session.add(
        FieldValue(
            application_id=application.id,
            field_key="hoa_fee_monthly",
            value="0.00",
            source=FieldSource.DEFAULT,
        )
    )
    await db_session.flush()
    scenario = await make_scenario(
        application,
        purchase_price=Decimal("300000.00"),
        down_payment_pct=Decimal("0.20"),
        strategy=StrategyType.PRIMARY,
    )
    await make_quote(scenario, rate=Decimal("7.000"), label="Par")
    await db_session.commit()

    before = await client.get(f"/api/v1/applications/{application.id}/pricing")
    assert before.status_code == 200
    monthly_tax_before = Decimal(before.json()["breakdown"]["monthly_tax"])
    assert monthly_tax_before == Decimal("300.00")  # 300000 * 0.012 / 12

    override = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate",
        json={"value": "0.02"},
    )
    assert override.status_code == 200

    after = await client.get(f"/api/v1/applications/{application.id}/pricing")
    assert after.status_code == 200
    body = after.json()
    assert body["has_stale_quotes"] is True
    tax_field = next(f for f in body["fields"] if f["field_key"] == "property_tax_annual_rate")
    assert tax_field["overridden"] is True
    assert tax_field["source"] == "lo_override"
    monthly_tax_after = Decimal(body["breakdown"]["monthly_tax"])
    assert monthly_tax_after == Decimal("500.00")  # 300000 * 0.02 / 12
    assert monthly_tax_after != monthly_tax_before
    assert Decimal(body["breakdown"]["total_monthly_payment"]) != Decimal(
        before.json()["breakdown"]["total_monthly_payment"]
    )


async def test_pricing_marcus_hale_golden_values(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC1: for Marcus Hale (STR) at 7.500%, 20% down on $342,000 -- loan
    $273,600.00, LTV 80.00%, P&I $1,913.05, with his real seeded tax and
    insurance field values (not hand-typed catalog numbers). Seeds him
    through the exact same pipeline `make demo-reset` runs (`seed_persona`),
    reads his real `field_values` off the GET pricing view, then feeds them
    into `/quotes/preview` at the golden combo.
    """
    user_result = await seed_users(db_session)
    await seed_providers(db_session)
    personas = {p["key"]: p for p in load_persona_fixtures()}
    marcus = personas["marcus_hale"]

    seed_result = await seed_persona(
        db_session, marcus, lo_id=user_result.lo_ids[0], s3_client=None
    )
    application = await db_session.get(Application, seed_result.application_id)
    assert application is not None
    assert application.requested_price == Decimal("342000.00")

    # Manager sees every LO's applications (`scope_applications`) --
    # simplest way to authenticate without hunting down which seeded LO
    # key owns this particular application id.
    await make_staff_session(role=UserRole.MANAGER)

    pricing_response = await client.get(f"/api/v1/applications/{application.id}/pricing")
    assert pricing_response.status_code == 200
    fields = {f["field_key"]: f for f in pricing_response.json()["fields"]}
    assert fields["property_tax_annual_rate"]["source"] == "smartasset"
    assert fields["homeowners_ins_annual"]["source"] == "steadily"
    assert fields["gross_annual_revenue_str"]["source"] == "airdna"

    tax_fraction = Decimal(fields["property_tax_annual_rate"]["value"])
    insurance_annual = Decimal(fields["homeowners_ins_annual"]["value"])
    str_gross_annual_revenue = Decimal(fields["gross_annual_revenue_str"]["value"])

    preview_response = await client.post(
        "/api/v1/quotes/preview",
        json={
            "purchase_price": "342000.00",
            "down_payment_amount": "68400.00",  # 20.00% of 342000.00
            "note_rate": "0.075",
            "strategy": "STR",
            "fico": marcus["fico"],
            "property_tax_annual_rate": str(tax_fraction),
            "insurance_annual_rate": str(insurance_annual / Decimal("342000.00")),
            "str_gross_annual_revenue": str(str_gross_annual_revenue),
        },
    )
    assert preview_response.status_code == 200
    body = preview_response.json()
    assert Decimal(body["down_payment_pct"]) == Decimal("0.2000")
    assert Decimal(body["down_payment_amount"]) == Decimal("68400.00")
    assert Decimal(body["loan_amount"]) == Decimal("273600.00")
    assert Decimal(body["ltv_pct"]) == Decimal("0.8000")
    assert Decimal(body["monthly_pi"]) == Decimal("1913.05")
