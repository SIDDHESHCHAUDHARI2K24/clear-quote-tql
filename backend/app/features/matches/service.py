"""`compute_matches_for_package` -- the property-match engine (spec.md's
`find_matches`; named per phase-p3-p4-plan.md D4, plan.md Decision 6).

A TBD borrower with `recommend_matches` on gets up to 3 seeded listings run
through the exact same `quote_engine` their own recommended quote used --
each candidate's `ScenarioInputs` differs only in `purchase_price` (the
listing's price) and the enrichment fields a *different* address would
actually enrich to (tax rate, insurance rate, market rent/STR revenue, all
from the same mock providers `pricing/enrichment/service.py` calls for the
subject property). Down payment %, note rate, discount points and FICO come
straight from the recommended quote/scenario -- never recomputed, never
re-picked.

No I/O beyond what's documented below; every money number is
`quote_engine.compute_quote` output, never derived by this module (AGENTS.md:
"Money math lives only in quote_engine").
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.core.errors import ValidationAppError
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.pricing.engine.quote_engine import (
    compute_quote,
    insurance_annual_rate_from_amount,
    match_ceiling_price,
    match_floor_price,
)
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.report.inputs import ReportMatchInput
from app.integrations.common.errors import IntegrationError
from app.integrations.insurance.mock import MockInsuranceClient
from app.integrations.property_search.models import ProviderListing
from app.integrations.rent.mock import MockRentClient
from app.integrations.str.mock import MockStrClient
from app.integrations.tax.mock import MockTaxClient

_MAX_MATCHES = 3
_LISTING_UNITS = 1
"""Every seeded listing is `property_type=single_family` (1 unit); rent/STR
provider fixtures are keyed `(zip, beds)` but only ever seeded at
`beds=1` -- the same convention CQ-013 established for the subject property
(`Property.number_of_units`, always 1 for single-family). Plan.md Decision
5."""


def _strategy_type(application: Application) -> StrategyType:
    """Small, feature-local copy of the same mapping
    `pricing/scenarios/service.py`/`portal/reports/versions.py` each already
    duplicate (private to their own modules) -- same convention, not a new
    one."""
    if application.occupancy is Occupancy.PRIMARY:
        return StrategyType.PRIMARY
    if application.strategy is Strategy.LTR:
        return StrategyType.LTR
    if application.strategy is Strategy.STR:
        return StrategyType.STR
    raise ValidationAppError(f"Application {application.id} has no strategy set")


def _format_baths(baths: Decimal) -> str:
    """Copy of `property_search/mock.py`'s own private helper -- small
    enough to duplicate rather than make public across features."""
    normalized = baths.normalize()
    return f"{normalized:f}" if normalized % 1 else f"{int(normalized)}"


@dataclass(frozen=True)
class _CandidateResult:
    match: ReportMatchInput
    rank_key: Decimal
    """What this candidate is sorted by: `monthly_cashflow` (LTR, descending),
    `dscr_ratio` (STR, descending), or `total_monthly_payment` (primary,
    ascending -- plan.md Decision 8)."""


async def _resolve_recommended_quote(db: AsyncSession, application: Application) -> Quote | None:
    """Plan.md Decision 7: `application.recommended_quote_id` is only set by
    CQ-018 (not yet merged when this item was built) -- fall back to the
    application's earliest-created scenario's "Par" quote, matching
    `seed/loader.py::apply_send_fixture`'s own `quote_ids[0]` convention."""
    if application.recommended_quote_id is not None:
        quote = await db.get(Quote, application.recommended_quote_id)
        if quote is not None:
            return quote

    scenario = (
        await db.execute(
            select(Scenario)
            .where(Scenario.application_id == application.id)
            .order_by(Scenario.created_at, Scenario.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if scenario is None:
        return None

    quotes = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.scenario_id == scenario.id)
                .order_by(Quote.created_at, Quote.id)
            )
        )
        .scalars()
        .all()
    )
    if not quotes:
        return None
    for quote in quotes:
        if quote.label == "Par":
            return quote
    return quotes[0]


async def _candidate_listings(
    db: AsyncSession,
    *,
    strategy: StrategyType,
    property_: Property,
    floor_price: Decimal,
    ceiling_price: Decimal,
) -> list[ProviderListing]:
    stmt = select(ProviderListing).where(
        ProviderListing.list_price >= floor_price,
        ProviderListing.list_price <= ceiling_price,
        ProviderListing.state.in_(property_.buy_box_states),
        ProviderListing.metro.in_(property_.buy_box_metros),
    )
    if strategy is StrategyType.STR:
        # Strategy fit (spec.md): "STR -> ranked by DSCR, STR-permitted
        # listings only." LTR and primary have no such extra filter (plan.md
        # Decision 2 -- the catalog has no "owner-occupant" listing
        # attribute, so primary uses the full candidate set).
        stmt = stmt.where(ProviderListing.str_permitted.is_(True))
    # No ORDER BY here on purpose: the final ranking in
    # `compute_matches_for_package` sorts on `(rank_key, matched_property_id)`,
    # an explicit total order that doesn't depend on the order these rows
    # arrive in (Postgres has no guaranteed row order without an ORDER BY).
    # A second `ORDER BY id` here would just make Postgres sort twice for
    # no behavior change.
    return list((await db.execute(stmt)).scalars().all())


async def _build_candidate(
    db: AsyncSession,
    *,
    listing: ProviderListing,
    strategy: StrategyType,
    base_fico: int,
    down_payment_pct: Decimal,
    note_rate: Decimal,
    discount_points_pct: Decimal,
    config: ConfigSnapshot,
) -> _CandidateResult | None:
    try:
        tax = await MockTaxClient(db).get_tax_rate(listing.state, listing.county)
        insurance = await MockInsuranceClient(db).get_insurance_estimate(
            listing.state, listing.list_price
        )
        market_rent_ltr: Decimal | None = None
        str_gross_annual_revenue: Decimal | None = None
        if strategy is StrategyType.LTR:
            rent = await MockRentClient(db).get_market_rent(listing.zip, _LISTING_UNITS)
            market_rent_ltr = rent.market_rent
        elif strategy is StrategyType.STR:
            revenue = await MockStrClient(db).get_str_revenue(listing.zip, _LISTING_UNITS)
            str_gross_annual_revenue = revenue.annual_revenue
    except IntegrationError:
        # Plan.md Decision 9: a provider failure (forced-fail toggle, or a
        # listing whose zip/state has no seeded row) drops that one
        # candidate rather than failing the whole matches list.
        return None

    inputs = ScenarioInputs(
        purchase_price=listing.list_price,
        down_payment_pct=down_payment_pct,
        note_rate=note_rate,
        strategy=strategy,
        fico=base_fico,
        property_tax_annual_rate=tax.annual_rate_pct / Decimal("100"),
        insurance_annual_rate=insurance_annual_rate_from_amount(
            listing.list_price, insurance.annual_premium
        ),
        discount_points_pct=discount_points_pct,
        market_rent_ltr=market_rent_ltr,
        str_gross_annual_revenue=str_gross_annual_revenue,
    )
    computation = compute_quote(inputs, config)

    bed_bath_sqft = f"{listing.beds} bd · {_format_baths(listing.baths)} ba · {listing.sqft:,} sqft"
    address = f"{listing.address}, {listing.city}, {listing.state} {listing.zip}"

    if strategy is StrategyType.PRIMARY:
        match = ReportMatchInput(
            matched_property_id=str(listing.id),
            property_image_url=listing.image_url,
            property_address=address,
            bed_bath_sqft=bed_bath_sqft,
            deal_grade_badge=listing.deal_grade.value,
            property_tagline=listing.tagline or "",
            price=listing.list_price,
            total_monthly_payment=computation.total_monthly_payment,
            rent_estimate=None,
            rent_label=None,
            monthly_cashflow=None,
            cash_to_close=computation.cash_to_close,
            cap_rate_pct=None,
            year1_tax_savings=None,
        )
        return _CandidateResult(match=match, rank_key=computation.total_monthly_payment)

    assert computation.monthly_cashflow is not None
    assert computation.dscr_ratio is not None
    assert computation.cap_rate_pct is not None
    assert computation.year_one_tax_savings is not None

    if strategy is StrategyType.LTR:
        rent_estimate = computation.qualifying_rent
        rent_label = "Market rent (LTR)"
        rank_key = computation.monthly_cashflow
    else:
        assert computation.str_gross_monthly_revenue is not None
        rent_estimate = computation.str_gross_monthly_revenue
        rent_label = "Gross STR revenue"
        rank_key = computation.dscr_ratio

    match = ReportMatchInput(
        matched_property_id=str(listing.id),
        property_image_url=listing.image_url,
        property_address=address,
        bed_bath_sqft=bed_bath_sqft,
        deal_grade_badge=listing.deal_grade.value,
        property_tagline=listing.tagline or "",
        price=listing.list_price,
        total_monthly_payment=computation.total_monthly_payment,
        rent_estimate=rent_estimate,
        rent_label=rent_label,
        monthly_cashflow=computation.monthly_cashflow,
        cash_to_close=computation.cash_to_close,
        cap_rate_pct=computation.cap_rate_pct,
        year1_tax_savings=computation.year_one_tax_savings,
    )
    return _CandidateResult(match=match, rank_key=rank_key)


async def compute_matches_for_package(
    db: AsyncSession, *, application: Application, recommended_quote: Quote | None
) -> list[ReportMatchInput]:
    """Returns up to 3 `ReportMatchInput`s for `application`, or `[]` when
    matches don't apply (specific address, `recommend_matches` off, no
    recommended quote/scenario to price from, or no candidates in band).

    `recommended_quote` is the option whose terms (down payment %, note
    rate, discount points, FICO) every candidate listing is priced with --
    the caller resolves it (CQ-019's draft builder, CQ-020's freeze, or this
    module's own `find_current_matches` for the live GET endpoint via
    `_resolve_recommended_quote`).
    """
    if application.requested_price is None or recommended_quote is None:
        return []

    property_ = (
        await db.execute(select(Property).where(Property.application_id == application.id))
    ).scalar_one_or_none()
    if property_ is None:
        return []
    if property_.address_status is not PropertyAddressStatus.TBD:
        return []
    if not property_.recommend_matches:
        return []
    if not property_.buy_box_states or not property_.buy_box_metros:
        return []

    strategy = _strategy_type(application)

    scenario = await db.get(Scenario, recommended_quote.scenario_id)
    if scenario is None:
        return []
    scenario_inputs = ScenarioInputs.model_validate(scenario.inputs)
    config = ConfigSnapshot.model_validate(scenario.config_snapshot)

    floor_price = match_floor_price(application.requested_price)
    ceiling_price = match_ceiling_price(application.requested_price)

    listings = await _candidate_listings(
        db,
        strategy=strategy,
        property_=property_,
        floor_price=floor_price,
        ceiling_price=ceiling_price,
    )

    candidates: list[_CandidateResult] = []
    for listing in listings:
        candidate = await _build_candidate(
            db,
            listing=listing,
            strategy=strategy,
            base_fico=scenario_inputs.fico,
            down_payment_pct=scenario_inputs.down_payment_pct,
            note_rate=recommended_quote.rate / Decimal("100"),
            discount_points_pct=recommended_quote.points,
            config=config,
        )
        if candidate is not None:
            candidates.append(candidate)

    # Strategy fit (spec.md): LTR by monthly cashflow descending, STR by
    # DSCR descending, primary by total monthly payment ascending (plan.md
    # Decision 8). Secondary sort on the listing's own id (`matched_
    # property_id`) makes a rank_key tie deterministic. `sign` flips the
    # primary key's direction while the id tie-break always stays ascending.
    sign = Decimal(1) if strategy is StrategyType.PRIMARY else Decimal(-1)
    candidates.sort(key=lambda c: (sign * c.rank_key, c.match.matched_property_id))

    return [c.match for c in candidates[:_MAX_MATCHES]]


async def find_current_matches(
    db: AsyncSession, application: Application
) -> list[ReportMatchInput]:
    """The live-computation path `GET /applications/{id}/matches` uses --
    resolves "the recommended quote" itself (Decision 7) instead of
    requiring the caller to already have one, unlike
    `compute_matches_for_package` (which CQ-019/CQ-020 call with a quote
    they've already resolved as part of building/freezing a package)."""
    recommended_quote = await _resolve_recommended_quote(db, application)
    return await compute_matches_for_package(
        db, application=application, recommended_quote=recommended_quote
    )
