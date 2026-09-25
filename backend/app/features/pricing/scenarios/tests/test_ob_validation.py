"""AC4: missing a required OB field returns HTTP 422 with CQ-004's pinned
error shape (persona 7, Aisha Coleman's "Cannot price: missing Occupancy" --
using `RepresentativeFICO` here since `applications.occupancy` is a
non-nullable column in this item's own schema, but the mechanism and shape
are identical for every required field, per spec.md's "and equivalent for
other fields").

Also covers the resolve direction (orchestrator requirement): once the
missing field is filled in, `validate_ob_required_fields` resolves the
`ob_required_field` flag it raised.
"""

from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.verification.models import Flag
from app.features.pricing.enrichment.service import (
    _OB_REQUIRED_FLAG_RULE,
    validate_ob_required_fields,
)
from app.integrations.common.errors import PricingValidationError
from app.integrations.tax.models import ProviderTaxRate
from conftest import StaffSession


async def _seed_tax(db_session: AsyncSession) -> None:
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


async def _flag(db_session: AsyncSession, application_id: object) -> Flag | None:
    return (
        await db_session.execute(
            select(Flag).where(
                Flag.application_id == application_id,
                Flag.field_key == "RepresentativeFICO",
                Flag.rule == _OB_REQUIRED_FLAG_RULE,
                Flag.resolved_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def test_missing_fico_raises_422_with_pinned_shape(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)

    with pytest.raises(PricingValidationError) as exc_info:
        await validate_ob_required_fields(db_session, application.id)

    assert exc_info.value.code == "PRICING_VALIDATION_ERROR"
    assert exc_info.value.status_code == 422
    assert exc_info.value.missing_fields == ["RepresentativeFICO"]
    assert exc_info.value.message == "Cannot price: missing RepresentativeFICO"


async def test_missing_field_writes_a_blocking_flag(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)

    with pytest.raises(PricingValidationError):
        await validate_ob_required_fields(db_session, application.id)

    flag = await _flag(db_session, application.id)
    assert flag is not None
    assert flag.tab == ApplicationTab.PRICING
    assert flag.severity.value == "blocking"


async def test_fixing_the_field_resolves_the_flag(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """Resolve direction (orchestrator requirement)."""
    application = await make_application(occupancy=Occupancy.PRIMARY)

    with pytest.raises(PricingValidationError):
        await validate_ob_required_fields(db_session, application.id)
    assert await _flag(db_session, application.id) is not None

    await set_field_value(application.id, "representative_fico", Decimal("740"))
    await db_session.commit()

    result = await validate_ob_required_fields(db_session, application.id)

    assert result is True
    assert await _flag(db_session, application.id) is None


async def test_scenario_create_route_propagates_pricing_validation_error(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """spec.md: every route that prices lets `PricingValidationError`
    propagate to CQ-004's `AppError` handler as a 422. `create_scenario`
    only reaches OB for LTR/STR (the two-pass DSCR loop); FICO/tax/
    insurance/rent are all present here so it's specifically the property's
    missing zip code (an OB-required field) that fails."""
    staff = await make_staff_session()
    application = await make_application(
        occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR, zip_code=None, lo=staff.user
    )
    await set_field_value(application.id, "representative_fico", Decimal("740"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2440.00"))
    await db_session.commit()

    response = await client.post(
        f"/api/v1/applications/{application.id}/scenarios",
        json={
            "purchase_price": "342000.00",
            "down_payment_pct": "0.25",
            "strategy": "LTR",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "PRICING_VALIDATION_ERROR"
    assert "ZipCode" in body["error"]["details"]["missing_fields"]


async def test_scenario_create_with_zero_purchase_price_is_422_not_500(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """PR review round (fresh stage-6, PR #9): `_gather_base_scenario_
    inputs` calls `quote_engine.insurance_annual_rate_from_amount`, which
    raises `NonPositivePriceError` (a plain `ValueError`) for a
    non-positive `purchase_price`. `ScenarioCreateRequest.purchase_price`
    has no `gt=0` constraint, so a zero price reaches the service layer --
    this must degrade to the same 422 shape as every other "can't price"
    guard in `_gather_base_scenario_inputs`, never a bare 500."""
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    await set_field_value(application.id, "representative_fico", Decimal("740"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await db_session.commit()

    response = await client.post(
        f"/api/v1/applications/{application.id}/scenarios",
        json={
            "purchase_price": "0.00",
            "down_payment_pct": "0.20",
            "strategy": "PRIMARY",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
