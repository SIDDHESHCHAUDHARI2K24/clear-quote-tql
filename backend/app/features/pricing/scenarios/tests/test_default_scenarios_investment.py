"""AC5: the investment default scenario set produces the collapsed Group A
only when the actual DSCR bucket matches the 1.00 assumption, and two
groups (Group A + Group B) otherwise.
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.features.applications.models import Application
from app.features.pricing.scenarios.service import create_default_scenarios
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram

# All fixtures use this scenario: $342,000 / 25% down (LTV 75%) / 1% tax /
# 0.5% insurance / $2,440 market rent, fico 740 -- at 7.500% par this DSCR
# lands ONE_TO_1_25 (~1.04); at 3.000% it lands GE_1_25 (~1.54). See
# `test_dscr_two_pass_loop.py`'s docstring for the same math.


def _seed_curve(db_session: AsyncSession, dscr_bucket: str, par_rate: Decimal) -> None:
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
                investor_name=f"Investor {dscr_bucket}-{index}",
                product_name="DSCR 30 Yr Fixed",
                program=RateSheetProgram.DSCR,
                base_rate=par_rate + offset,
                base_price=Decimal("100.000") - offset * Decimal("4"),
                min_fico=680,
                max_ltv=Decimal("80.00"),
                dscr_bucket=dscr_bucket,
                lock_days=30,
                active=True,
            )
        )


async def _prep_application(
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> Application:
    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("342000.00"),
    )
    await set_field_value(application.id, "representative_fico", Decimal("740"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2440.00"))
    return application


async def test_collapses_to_one_group_when_actual_bucket_matches_assumption(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _prep_application(make_application, set_field_value)
    _seed_curve(db_session, "ONE_TO_1_25", Decimal("7.500"))
    await db_session.commit()

    result = await create_default_scenarios(db_session, application.id)

    assert len(result.groups) == 1
    assert result.groups[0].collapsed is True
    assert result.groups[0].note == "same pricing tier as the 1.00 assumption"
    assert len(result.groups[0].quote_ids) == 2  # Par + Buydown


async def test_produces_two_groups_when_actual_bucket_differs(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _prep_application(make_application, set_field_value)
    # Group A prices at assumed ONE_TO_1_25 but the seeded rate (3.000%) is
    # low enough that the *actual* DSCR lands GE_1_25 -> Group B triggers,
    # and its own re-price at GE_1_25 finds the same rate -> converges.
    _seed_curve(db_session, "ONE_TO_1_25", Decimal("3.000"))
    _seed_curve(db_session, "GE_1_25", Decimal("3.000"))
    await db_session.commit()

    result = await create_default_scenarios(db_session, application.id)

    assert len(result.groups) == 2
    group_a, group_b = result.groups
    assert group_a.collapsed is False
    assert group_a.note is None
    assert group_b.collapsed is False
    assert group_a.scenario_id != group_b.scenario_id
    assert len(result.scenario_ids) == 2
    assert len(result.quote_ids) == len(set(result.quote_ids))  # no duplicate quote ids
