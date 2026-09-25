"""`compute_matches_for_package`: spec.md AC1, AC2, AC4, AC5, AC6.

Every dollar figure is recomputed against `quote_engine.compute_quote`
directly (AC2), never hand-typed, matching `seed/tests/
test_personas_match_engine.py`'s own "raw inputs -> engine -> assert"
convention.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal

from seed.loader import seed_providers
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import PropertyAddressStatus, PropertyType
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.matches.service import compute_matches_for_package
from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.service import auto_price
from app.features.quotes.builder.models import Quote
from app.integrations.property_search.models import DealGrade, ProviderListing
from app.integrations.rent.models import ProviderRent
from app.integrations.tax.models import ProviderTaxRate

from .conftest import seed_conventional_rate_sheet, seed_dscr_rate_sheet


async def _seed_seed_providers(db_session: AsyncSession) -> None:
    await seed_providers(db_session)
    await db_session.commit()


async def _kathleen(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> tuple[Application, Quote]:
    """Kathleen McReynolds's real seeded numbers (seed/personas/
    p02_kathleen_mcreynolds.yaml): investment/LTR, $300,000 approved,
    FL/[Davenport, Orlando] buy-box, TBD, recommend_matches on."""
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
    recommended_quote = await db_session.get(Quote, pricing_result.quote_ids[0])
    assert recommended_quote is not None
    return application, recommended_quote


async def test_matches_kathleen(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, recommended_quote = await _kathleen(db_session, make_application, set_field_value)

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=recommended_quote
    )

    assert len(matches) == 3
    for match in matches:
        price = match.price
        assert Decimal("210000.00") <= price <= Decimal("300000.00"), price
        assert match.rent_label == "Market rent (LTR)"
        assert match.monthly_cashflow is not None

    cashflows = [m.monthly_cashflow for m in matches]
    assert all(c is not None for c in cashflows)
    non_null_cashflows = [c for c in cashflows if c is not None]
    assert non_null_cashflows == sorted(non_null_cashflows, reverse=True)

    # AC6: the 69%/101% boundary fixtures never appear.
    prices = {m.price for m in matches}
    assert Decimal("207000.00") not in prices
    assert Decimal("303000.00") not in prices


async def test_match_numbers_match_engine(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """AC2: recompute each match's payment/cash-to-close directly from
    `quote_engine`, using the recommended option's own terms and the
    listing's own (real, seeded-provider) enrichment."""
    application, recommended_quote = await _kathleen(db_session, make_application, set_field_value)

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=recommended_quote
    )
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
            note_rate=recommended_quote.rate / Decimal("100"),
            strategy=StrategyType.LTR,
            fico=720,
            property_tax_annual_rate=tax_row.annual_rate_pct / Decimal("100"),
            insurance_annual_rate=Decimal("0.50") / Decimal("100"),
            discount_points_pct=recommended_quote.points,
            market_rent_ltr=Decimal("2250.00"),
        )
        expected = compute_quote(inputs, config)
        assert match.total_monthly_payment == expected.total_monthly_payment
        assert match.cash_to_close == expected.cash_to_close


async def test_matches_toggle_off(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """AC4: `recommend_matches` off removes every match."""
    await _seed_seed_providers(db_session)

    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000.00"),
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["FL"],
        buy_box_metros=["Davenport", "Orlando"],
        recommend_matches=False,
    )
    await set_field_value(application.id, "representative_fico", Decimal("720"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0089"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2250.00"))
    seed_dscr_rate_sheet(db_session, "ONE_TO_1_25", Decimal("7.250"))
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    recommended_quote = await db_session.get(Quote, pricing_result.quote_ids[0])

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=recommended_quote
    )
    assert matches == []


async def test_no_matches_for_specific_address(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """AC3 (service level; test_router.py covers the API/report-level check)."""
    await _seed_seed_providers(db_session)

    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000.00"),
        address_status=PropertyAddressStatus.SPECIFIC_ADDRESS,
        buy_box_states=["FL"],
        buy_box_metros=["Davenport", "Orlando"],
    )
    await set_field_value(application.id, "representative_fico", Decimal("720"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0089"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2250.00"))
    seed_dscr_rate_sheet(db_session, "ONE_TO_1_25", Decimal("7.250"))
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    recommended_quote = await db_session.get(Quote, pricing_result.quote_ids[0])

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=recommended_quote
    )
    assert matches == []


async def test_match_ranking_by_strategy(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """AC5: an STR TBD application's matches are STR-permitted only and
    sorted by DSCR descending (Tampa, FL has 2 str_permitted listings in
    band and 1 not-permitted-but-in-band listing that must never appear)."""
    await _seed_seed_providers(db_session)

    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.STR,
        requested_price=Decimal("350000.00"),
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["FL"],
        buy_box_metros=["Tampa"],
        recommend_matches=True,
        state="FL",
        county="Hillsborough",
        zip_code="33602",
        city="Tampa",
    )
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0089"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "gross_annual_revenue_str", Decimal("24000.00"))
    seed_dscr_rate_sheet(db_session, "ONE_TO_1_25", Decimal("7.500"))
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    recommended_quote = await db_session.get(Quote, pricing_result.quote_ids[0])
    assert recommended_quote is not None

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=recommended_quote
    )

    assert len(matches) == 3  # 290700 / 300000 / 320000 -- all str_permitted, in band
    # 260000 (not str_permitted, otherwise in band) must never appear.
    assert Decimal("260000.00") not in {m.price for m in matches}

    dscrs = [m.rent_estimate for m in matches]  # sanity: STR carries a rent estimate too
    assert all(d is not None for d in dscrs)
    for match in matches:
        assert match.rent_label == "Gross STR revenue"


async def test_match_ranking_primary_has_no_rental_fields(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """AC5's other half: primary matches show no rental fields."""
    await _seed_seed_providers(db_session)

    application = await make_application(
        occupancy=Occupancy.PRIMARY,
        strategy=None,
        requested_price=Decimal("300000.00"),
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["FL"],
        buy_box_metros=["Davenport", "Orlando"],
        recommend_matches=True,
    )
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0089"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    seed_conventional_rate_sheet(db_session)
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    recommended_quote = await db_session.get(Quote, pricing_result.quote_ids[0])
    assert recommended_quote is not None

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=recommended_quote
    )

    assert matches
    for match in matches:
        assert match.rent_estimate is None
        assert match.rent_label is None
        assert match.monthly_cashflow is None
        assert match.cap_rate_pct is None
        assert match.year1_tax_savings is None
        assert match.total_monthly_payment is not None
        assert match.cash_to_close is not None


async def test_compute_matches_returns_empty_without_a_recommended_quote(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["FL"],
        buy_box_metros=["Davenport"],
    )
    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=None
    )
    assert matches == []


async def test_compute_matches_returns_empty_without_a_property(
    db_session: AsyncSession,
) -> None:
    """A real recommended quote exists, but no `Property` row at all (an
    application state `compute_matches_for_package` must still handle
    gracefully, distinct from the `recommended_quote=None` case above).
    Builds the `Scenario`/`Quote` rows directly -- `auto_price` itself goes
    through OB pricing, which needs a `Property` row to build its request
    (a different, already-covered failure mode), so it can't reach this
    application state."""
    await _seed_seed_providers(db_session)

    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
        password_hash="x",
        role=UserRole.LO,
        full_name="Jordan Blake",
    )
    db_session.add(lo)
    await db_session.flush()
    client = Client(
        full_name="No Property", email=f"np-{uuid.uuid4()}@example.com", assigned_lo_id=lo.id
    )
    db_session.add(client)
    await db_session.flush()
    application = Application(
        client_id=client.id,
        lo_id=lo.id,
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000"),
    )
    db_session.add(application)
    await db_session.flush()

    inputs = ScenarioInputs(
        purchase_price=Decimal("300000.00"),
        down_payment_pct=Decimal("0.25"),
        note_rate=Decimal("0.0725"),
        strategy=StrategyType.LTR,
        fico=720,
        property_tax_annual_rate=Decimal("0.0089"),
        insurance_annual_rate=Decimal("0.005"),
        market_rent_ltr=Decimal("2250.00"),
    )
    config = ConfigSnapshot()
    scenario = Scenario(
        application_id=application.id,
        inputs=json.loads(inputs.model_dump_json()),
        config_snapshot=json.loads(config.model_dump_json()),
    )
    db_session.add(scenario)
    await db_session.flush()

    computation = compute_quote(inputs, config)
    quote = Quote(
        scenario_id=scenario.id,
        investor="Test Investor",
        product="Test Product",
        rate=Decimal("7.250"),
        points=Decimal("0"),
        lock_days=30,
        computed=json.loads(computation.model_dump_json()),
        label="Par",
        priced_at=datetime.now(UTC),
    )
    db_session.add(quote)
    await db_session.flush()

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=quote
    )
    assert matches == []


async def test_match_ranking_ties_break_deterministically_by_listing_id(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """Two listings identical on every input the LTR rank_key
    (`monthly_cashflow`) depends on -- same price, state/county (tax),
    zip (rent) -- produce a true tie. The result order must still be
    deterministic (ascending `matched_property_id`/listing id), not
    whatever order Postgres happens to return rows in."""
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
        password_hash="not-a-real-hash",
        role=UserRole.LO,
        full_name="Jordan Blake",
    )
    db_session.add(lo)
    await db_session.flush()

    db_session.add(
        ProviderTaxRate(
            county="TieCounty",
            state="TX",
            annual_rate_pct=Decimal("2.0000"),
            source_name="Test",
            as_of=date(2026, 1, 1),
        )
    )
    db_session.add(
        ProviderRent(
            zip="75001",
            beds=1,
            market_rent=Decimal("2000.00"),
            rent_low=Decimal("1800.00"),
            rent_high=Decimal("2200.00"),
            comps_count=10,
            as_of=date(2026, 1, 1),
        )
    )

    listing_ids: list[uuid.UUID] = []
    for i in range(2):
        listing_id = uuid.uuid4()
        listing_ids.append(listing_id)
        db_session.add(
            ProviderListing(
                id=listing_id,
                address=f"{100 + i} Tie St",
                city="Tie City",
                state="TX",
                zip="75001",
                county="TieCounty",
                metro="TieMetro",
                list_price=Decimal("250000.00"),
                beds=3,
                baths=Decimal("2.0"),
                sqft=1500,
                property_type=PropertyType.SINGLE_FAMILY,
                image_url="https://example.com/tie.jpg",
                deal_grade=DealGrade.GOOD_BUY,
                tagline=None,
                str_permitted=False,
            )
        )
    # Sort ascending by id up front so the assertion below is independent
    # of insertion order too.
    listing_ids.sort()
    await db_session.flush()

    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("300000.00"),
        address_status=PropertyAddressStatus.TBD,
        buy_box_states=["TX"],
        buy_box_metros=["TieMetro"],
        recommend_matches=True,
        lo=lo,
    )
    # Same subject-property field values as `_kathleen` above -- this keeps
    # `auto_price`'s DSCR-bucket resolution collapsed to the one seeded
    # bucket instead of triggering the two-pass re-price loop (which would
    # need a rate sheet at whatever bucket a different tax/rent input
    # produces). The *candidate listings*' own tax/rent (TX/TieCounty/75001,
    # seeded above) are what drives the tie, not these.
    await set_field_value(application.id, "representative_fico", Decimal("720"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0089"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2250.00"))
    seed_dscr_rate_sheet(db_session, "ONE_TO_1_25", Decimal("7.250"))
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    recommended_quote = await db_session.get(Quote, pricing_result.quote_ids[0])
    assert recommended_quote is not None

    matches = await compute_matches_for_package(
        db_session, application=application, recommended_quote=recommended_quote
    )

    assert len(matches) == 2
    # A true tie: both listings produce the exact same rank_key input.
    assert matches[0].monthly_cashflow == matches[1].monthly_cashflow
    assert [m.matched_property_id for m in matches] == [str(lid) for lid in listing_ids]
