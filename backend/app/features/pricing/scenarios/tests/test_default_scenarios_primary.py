"""AC6: the primary default scenario set produces one group when the chosen
down payment >= 20%, and two groups (second = Par only, at exactly 20%
down) when < 20%.
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy
from app.features.applications.models import Application
from app.features.pricing.scenarios.service import create_default_scenarios
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram


def _seed_conventional_curve(db_session: AsyncSession) -> None:
    offsets = [
        Decimal("-0.250"),
        Decimal("-0.125"),
        Decimal("0.000"),
        Decimal("0.125"),
        Decimal("0.250"),
    ]
    for index, offset in enumerate(offsets):
        db_session.add(
            ProviderRateSheet(
                investor_name=f"Investor {index}",
                product_name="Conventional 30 Yr Fixed",
                program=RateSheetProgram.CONVENTIONAL,
                base_rate=Decimal("7.000") + offset,
                base_price=Decimal("100.000") - offset * Decimal("4"),
                min_fico=680,
                max_ltv=Decimal("97.00"),
                lock_days=30,
                active=True,
            )
        )


async def _prep_application(
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> Application:
    application = await make_application(
        occupancy=Occupancy.PRIMARY, requested_price=Decimal("300000.00")
    )
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    return application


async def test_one_group_when_down_payment_at_or_above_20_percent(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _prep_application(make_application, set_field_value)
    _seed_conventional_curve(db_session)
    await db_session.commit()

    result = await create_default_scenarios(
        db_session, application.id, down_payment_pct=Decimal("0.25")
    )

    assert len(result.groups) == 1
    assert len(result.groups[0].quote_ids) == 2  # Par + Buydown


async def test_two_groups_when_down_payment_below_20_percent(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _prep_application(make_application, set_field_value)
    _seed_conventional_curve(db_session)
    await db_session.commit()

    result = await create_default_scenarios(
        db_session, application.id, down_payment_pct=Decimal("0.15")
    )

    assert len(result.groups) == 2
    group_a, group_b = result.groups
    assert len(group_a.quote_ids) == 2  # Par + Buydown at 15% down
    assert len(group_b.quote_ids) == 1  # Par only at 20% down
    assert group_a.scenario_id != group_b.scenario_id


async def test_default_down_payment_is_20_percent_when_not_given(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _prep_application(make_application, set_field_value)
    _seed_conventional_curve(db_session)
    await db_session.commit()

    result = await create_default_scenarios(db_session, application.id)

    assert len(result.groups) == 1
