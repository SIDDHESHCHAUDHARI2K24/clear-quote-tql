"""`get_pricing_view` (CQ-017 spec.md): current scenario inputs, every
pricing-overridable enriched field with its badge/override state, the
engine breakdown, and the stale-quotes flag.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FieldSource, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.verification.models import FieldValue
from app.features.pricing.engine.types import StrategyType
from app.features.pricing.panel.service import get_pricing_view
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.integrations.tax.models import ProviderTaxRate
from conftest import StaffSession


async def test_pricing_view_with_scenario_and_par_quote(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[FieldValue]],
    make_scenario: Callable[..., Awaitable[Scenario]],
    make_quote: Callable[..., Awaitable[Quote]],
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)
    await set_field_value(application.id, "representative_fico", Decimal("740"), "credit_bureau")
    await set_field_value(
        application.id, "property_tax_annual_rate", Decimal("0.012"), "smartasset"
    )
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1800.00"), "steadily")
    await set_field_value(application.id, "hoa_fee_monthly", Decimal("0.00"), "default")
    scenario = await make_scenario(
        application,
        purchase_price=Decimal("300000.00"),
        down_payment_pct=Decimal("0.20"),
        strategy=StrategyType.PRIMARY,
        property_tax_annual_rate=Decimal("0.012"),
        insurance_annual_rate=Decimal("1800.00") / Decimal("300000.00"),
    )
    await make_quote(scenario, rate=Decimal("7.000"), label="Par")
    await db_session.commit()

    view = await get_pricing_view(db_session, application)

    assert view.inputs.purchase_price == Decimal("300000.00")
    assert view.inputs.down_payment_pct == Decimal("0.20")
    assert view.inputs.strategy is StrategyType.PRIMARY
    assert view.inputs.fico == 740
    assert view.inputs.insurance_annual_rate == Decimal("1800.00") / Decimal("300000.00")
    assert view.note_rate == Decimal("0.07")
    assert view.breakdown is not None
    assert view.breakdown.loan_amount == Decimal("240000.00")
    assert view.breakdown.ltv_pct == Decimal("0.8000")
    assert not view.has_stale_quotes

    field_keys = {f.field_key for f in view.fields}
    assert field_keys == {"property_tax_annual_rate", "homeowners_ins_annual", "hoa_fee_monthly"}
    tax_field = next(f for f in view.fields if f.field_key == "property_tax_annual_rate")
    assert tax_field.source == FieldSource.SMARTASSET
    assert tax_field.overridden is False
    assert tax_field.original_value is None


async def test_pricing_view_overridden_field_shows_original_value(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
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
    row = FieldValue(
        application_id=application.id,
        field_key="property_tax_annual_rate",
        value="0.0250",
        source=FieldSource.LO_OVERRIDE,
        overridden_by=staff.user.id,
        overridden_at=datetime.now(UTC),
    )
    db_session.add(row)
    await db_session.commit()

    view = await get_pricing_view(db_session, application)

    tax_field = next(f for f in view.fields if f.field_key == "property_tax_annual_rate")
    assert tax_field.overridden is True
    assert tax_field.value == "0.0250"
    assert tax_field.source == FieldSource.LO_OVERRIDE
    assert tax_field.original_value == Decimal("0.6010") / Decimal("100")


async def test_pricing_view_no_scenario_yet_builds_defaults_from_field_values(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[FieldValue]],
) -> None:
    application = await make_application(
        occupancy=Occupancy.PRIMARY, requested_price=Decimal("400000.00")
    )
    await set_field_value(application.id, "representative_fico", Decimal("740"), "credit_bureau")
    await set_field_value(
        application.id, "property_tax_annual_rate", Decimal("0.012"), "smartasset"
    )
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("2000.00"), "steadily")
    await db_session.commit()

    view = await get_pricing_view(db_session, application)

    assert view.inputs.purchase_price == Decimal("400000.00")
    assert view.inputs.down_payment_pct == Decimal("0.20")  # primary default
    assert view.note_rate is None
    assert view.breakdown is None  # no quote yet -> no rate -> can't price
    assert not view.has_stale_quotes


async def test_pricing_view_investment_defaults_to_25_pct_down(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.STR,
        requested_price=Decimal("342000.00"),
    )
    await db_session.commit()

    view = await get_pricing_view(db_session, application)

    assert view.inputs.strategy is StrategyType.STR
    assert view.inputs.down_payment_pct == Decimal("0.25")
    assert view.inputs.prepayment_penalty_years == 5


async def test_pricing_view_non_positive_purchase_price_degrades_to_no_breakdown(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[FieldValue]],
) -> None:
    """Review finding: a non-positive purchase price must never reach
    `insurance_annual_rate_from_amount`'s `NonPositivePriceError` as a
    500 -- degrades to a `None` breakdown like any other "can't price
    yet" case."""
    application = await make_application(
        occupancy=Occupancy.PRIMARY, requested_price=Decimal("0.00")
    )
    await set_field_value(application.id, "representative_fico", Decimal("740"), "credit_bureau")
    await set_field_value(
        application.id, "property_tax_annual_rate", Decimal("0.012"), "smartasset"
    )
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1800.00"), "steadily")
    await db_session.commit()

    view = await get_pricing_view(db_session, application)

    assert view.breakdown is None
    assert view.inputs.purchase_price == Decimal("0.00")


async def test_pricing_view_has_stale_quotes_true(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
    make_quote: Callable[..., Awaitable[Quote]],
) -> None:
    application = await make_application(occupancy=Occupancy.PRIMARY)
    scenario = await make_scenario(application)
    await make_quote(scenario, stale=True)
    await db_session.commit()

    view = await get_pricing_view(db_session, application)

    assert view.has_stale_quotes is True
