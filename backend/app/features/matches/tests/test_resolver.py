"""`_resolve_recommended_quote`/`find_current_matches` (service.py
`_resolve_recommended_quote` ~86-124, `find_current_matches` ~320-331):
the resolver `GET /applications/{id}/matches` uses (via
`find_current_matches`) to pick which quote's terms price every candidate
listing when the caller hasn't already resolved one itself (unlike
CQ-019/CQ-020's draft/send flow, which always passes its own
`recommended_quote`). Plan.md Decision 7.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from seed.loader import seed_providers
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.property.models import PropertyAddressStatus
from app.features.matches.service import find_current_matches
from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.service import auto_price
from app.features.quotes.builder.models import Quote
from app.integrations.tax.models import ProviderTaxRate

from .conftest import seed_dscr_rate_sheet


async def _seed_seed_providers(db_session: AsyncSession) -> None:
    await seed_providers(db_session)
    await db_session.commit()


async def test_find_current_matches_uses_recommended_quote_id(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """(a): `application.recommended_quote_id` points at a non-Par,
    non-first quote (the "Buydown" quote `auto_price` creates alongside
    "Par" in the same scenario) -- matches must be priced with *that*
    quote's own rate/points, not the resolver's Par-of-earliest-scenario
    fallback."""
    await _seed_seed_providers(db_session)

    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000.00"),
        first_name="Kathleen",
        last_name="McReynolds",
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

    pricing_result = await auto_price(db_session, application.id)
    assert len(pricing_result.quote_ids) >= 2, "fixture must produce a Par + Buydown pair"
    buydown_quote = await db_session.get(Quote, pricing_result.quote_ids[1])
    assert buydown_quote is not None
    assert buydown_quote.label != "Par"

    par_quote = await db_session.get(Quote, pricing_result.quote_ids[0])
    assert par_quote is not None
    assert buydown_quote.rate != par_quote.rate or buydown_quote.points != par_quote.points

    application.recommended_quote_id = buydown_quote.id
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    matches = await find_current_matches(db_session, application)
    assert matches

    tax_row = (
        await db_session.execute(
            select(ProviderTaxRate).where(
                ProviderTaxRate.state == "FL", ProviderTaxRate.county == "Polk"
            )
        )
    ).scalar_one()
    config = ConfigSnapshot()
    for match in matches:
        inputs = ScenarioInputs(
            purchase_price=match.price,
            down_payment_pct=Decimal("0.25"),
            note_rate=buydown_quote.rate / Decimal("100"),
            strategy=StrategyType.LTR,
            fico=720,
            property_tax_annual_rate=tax_row.annual_rate_pct / Decimal("100"),
            insurance_annual_rate=Decimal("0.50") / Decimal("100"),
            discount_points_pct=buydown_quote.points,
            market_rent_ltr=Decimal("2250.00"),
        )
        expected = compute_quote(inputs, config)
        assert match.total_monthly_payment == expected.total_monthly_payment
        assert match.cash_to_close == expected.cash_to_close

        # Sanity: the Par quote's own terms would have produced a
        # *different* number -- otherwise this test can't tell the two
        # quotes apart.
        par_inputs = ScenarioInputs(
            purchase_price=match.price,
            down_payment_pct=Decimal("0.25"),
            note_rate=par_quote.rate / Decimal("100"),
            strategy=StrategyType.LTR,
            fico=720,
            property_tax_annual_rate=tax_row.annual_rate_pct / Decimal("100"),
            insurance_annual_rate=Decimal("0.50") / Decimal("100"),
            discount_points_pct=par_quote.points,
            market_rent_ltr=Decimal("2250.00"),
        )
        par_expected = compute_quote(par_inputs, config)
        assert match.total_monthly_payment != par_expected.total_monthly_payment


async def test_find_current_matches_falls_back_to_earliest_scenarios_par_quote(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    """(b): `application.recommended_quote_id` is unset and there are
    several scenarios, each with several quotes -- the resolver must fall
    back to the *earliest-created* scenario's `"Par"` quote (Decision 7),
    not the first quote row it happens to see and not a later scenario's
    Par."""
    await _seed_seed_providers(db_session)

    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000.00"),
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["FL"],
        buy_box_metros=["Davenport", "Orlando"],
        recommend_matches=True,
    )
    assert application.recommended_quote_id is None

    now = datetime.now(UTC)
    config = ConfigSnapshot()

    def _inputs(fico: int) -> ScenarioInputs:
        return ScenarioInputs(
            purchase_price=Decimal("300000.00"),
            down_payment_pct=Decimal("0.25"),
            note_rate=Decimal("0.07"),
            strategy=StrategyType.LTR,
            fico=fico,
            property_tax_annual_rate=Decimal("0.0089"),
            insurance_annual_rate=Decimal("0.005"),
            market_rent_ltr=Decimal("2250.00"),
        )

    async def _make_scenario_with_quotes(
        *, created_at: datetime, fico: int, quote_specs: list[tuple[str, Decimal, Decimal]]
    ) -> Scenario:
        inputs = _inputs(fico)
        scenario = Scenario(
            id=uuid.uuid4(),
            application_id=application.id,
            inputs=json.loads(inputs.model_dump_json()),
            config_snapshot=json.loads(config.model_dump_json()),
            created_at=created_at,
        )
        db_session.add(scenario)
        await db_session.flush()
        for label, rate, points in quote_specs:
            computation = compute_quote(inputs, config)
            db_session.add(
                Quote(
                    scenario_id=scenario.id,
                    investor="Test Investor",
                    product="Test Product",
                    rate=rate,
                    points=points,
                    lock_days=30,
                    computed=json.loads(computation.model_dump_json()),
                    label=label,
                    priced_at=now,
                )
            )
        await db_session.flush()
        return scenario

    # Earliest scenario: a Buydown quote persisted *before* its own Par
    # quote (so a naive "first quote row" resolver would pick the wrong
    # one), fico=700.
    earliest_scenario = await _make_scenario_with_quotes(
        created_at=now - timedelta(hours=2),
        fico=700,
        quote_specs=[
            ("Buydown", Decimal("6.750"), Decimal("0.500")),
            ("Par", Decimal("7.000"), Decimal("0")),
        ],
    )
    # Later scenario: its own Par quote, fico=750 -- must never be picked.
    await _make_scenario_with_quotes(
        created_at=now - timedelta(hours=1),
        fico=750,
        quote_specs=[("Par", Decimal("7.500"), Decimal("0"))],
    )
    await db_session.commit()

    expected_par = (
        await db_session.execute(
            select(Quote).where(Quote.scenario_id == earliest_scenario.id, Quote.label == "Par")
        )
    ).scalar_one()
    assert expected_par.rate == Decimal("7.000")

    matches = await find_current_matches(db_session, application)
    assert matches

    tax_row = (
        await db_session.execute(
            select(ProviderTaxRate).where(
                ProviderTaxRate.state == "FL", ProviderTaxRate.county == "Polk"
            )
        )
    ).scalar_one()
    for match in matches:
        inputs = ScenarioInputs(
            purchase_price=match.price,
            down_payment_pct=Decimal("0.25"),
            note_rate=expected_par.rate / Decimal("100"),
            strategy=StrategyType.LTR,
            fico=700,
            property_tax_annual_rate=tax_row.annual_rate_pct / Decimal("100"),
            insurance_annual_rate=Decimal("0.50") / Decimal("100"),
            discount_points_pct=expected_par.points,
            market_rent_ltr=Decimal("2250.00"),
        )
        expected = compute_quote(inputs, config)
        assert match.total_monthly_payment == expected.total_monthly_payment
        assert match.cash_to_close == expected.cash_to_close
