"""AC8: `run_two_pass_dscr` re-prices exactly once when the bucket flips,
stops at 2 passes, and sets `bucket_flipped=True` plus a `flags` row when it
still disagrees after pass 2. Also covers the resolve direction (orchestrator
requirement): a stable/converged run resolves any previous `flags` row.
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.verification.models import Flag
from app.features.applications.verification.service import write_flag
from app.features.pricing.engine.types import (
    ConfigSnapshot,
    DSCRBucket,
    ScenarioInputs,
    StrategyType,
)
from app.features.pricing.scenarios.dscr_loop import DSCR_BUCKET_UNSTABLE_RULE, run_two_pass_dscr
from app.integrations.pricing.schemas import PricedProductDTO

_BASE_INPUTS = ScenarioInputs(
    purchase_price=Decimal("342000.00"),
    down_payment_pct=Decimal("0.20"),
    note_rate=Decimal("0"),
    strategy=StrategyType.LTR,
    fico=740,
    property_tax_annual_rate=Decimal("0.01"),
    insurance_annual_rate=Decimal("0.005"),
    market_rent_ltr=Decimal("2440.00"),
)
_CONFIG = ConfigSnapshot()


def _product(note_rate: str) -> PricedProductDTO:
    return PricedProductDTO(
        investor_name="Deephaven",
        product_name="Investor Solutions DSCR 30 Yr Fixed",
        lock_period_days=30,
        note_rate=Decimal(note_rate),
        price_pct=Decimal("100.000"),
        discount_points_pct=Decimal("0"),
        discount_points_amount=Decimal("0"),
        is_par_rate=True,
        is_buydown_rate=False,
    )


async def _find_flag(db_session: AsyncSession, application_id: object) -> Flag | None:
    return (
        await db_session.execute(
            select(Flag).where(
                Flag.application_id == application_id,
                Flag.field_key == "dscr_ratio",
                Flag.rule == DSCR_BUCKET_UNSTABLE_RULE,
                Flag.resolved_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def test_converges_on_pass_one_when_actual_bucket_matches_assumption(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)

    async def price_par_at_dscr(dscr: Decimal) -> PricedProductDTO:
        # A high enough rate that DSCR lands in ONE_TO_1_25 on the first try.
        return _product("7.500")

    result = await run_two_pass_dscr(
        db_session, application.id, _BASE_INPUTS, _CONFIG, price_par_at_dscr
    )

    assert result.passes == 1
    assert result.bucket_flipped is False
    assert result.computation.dscr_bucket == DSCRBucket.ONE_TO_1_25


async def test_reprices_once_when_bucket_flips_and_then_converges(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)
    call_count = 0

    async def price_par_at_dscr(dscr: Decimal) -> PricedProductDTO:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Pass 1 assumes ONE_TO_1_25 (rate 7.5) but actual DSCR lands
            # GE_1_25 at that rate -- forces pass 2.
            return _product("3.000")
        # Pass 2 re-prices at GE_1_25's representative DSCR; give a rate
        # whose actual bucket also lands GE_1_25 -> converges.
        return _product("3.000")

    result = await run_two_pass_dscr(
        db_session, application.id, _BASE_INPUTS, _CONFIG, price_par_at_dscr
    )

    assert call_count == 2
    assert result.passes == 2
    assert result.bucket_flipped is False
    assert result.computation.dscr_bucket == DSCRBucket.GE_1_25


async def test_flip_flop_keeps_lower_dscr_and_writes_warning_flag(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)
    call_count = 0

    async def price_par_at_dscr(dscr: Decimal) -> PricedProductDTO:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Pass 1 assumes ONE_TO_1_25 (rate high) -> actual lands GE_1_25.
            return _product("3.000")
        # Pass 2 assumes GE_1_25 -> give a very high rate so actual DSCR
        # drops back below 1.25 (a different bucket than assumed) -> flip.
        return _product("9.000")

    result = await run_two_pass_dscr(
        db_session,
        application.id,
        _BASE_INPUTS,
        _CONFIG,
        price_par_at_dscr,
        assumed_bucket=DSCRBucket.ONE_TO_1_25,
    )

    assert call_count == 2
    assert result.passes == 2
    assert result.bucket_flipped is True
    # The lower-DSCR (higher note rate -> lower DSCR) result is kept.
    assert result.par_product.note_rate == Decimal("9.000")

    flag = await _find_flag(db_session, application.id)
    assert flag is not None
    assert flag.severity == FlagSeverity.WARNING
    assert flag.tab == ApplicationTab.PRICING


async def test_stable_run_resolves_a_previously_raised_unstable_flag(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """Resolve direction (orchestrator requirement): a later stable/
    converged run must resolve any `dscr_bucket_unstable` flag a prior
    unstable run raised."""
    application = await make_application(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)
    await write_flag(
        db_session,
        application.id,
        ApplicationTab.PRICING,
        "dscr_ratio",
        DSCR_BUCKET_UNSTABLE_RULE,
        FlagSeverity.WARNING,
    )
    await db_session.commit()
    assert await _find_flag(db_session, application.id) is not None

    async def price_par_at_dscr(dscr: Decimal) -> PricedProductDTO:
        return _product("7.500")  # converges on pass 1

    await run_two_pass_dscr(db_session, application.id, _BASE_INPUTS, _CONFIG, price_par_at_dscr)

    assert await _find_flag(db_session, application.id) is None
