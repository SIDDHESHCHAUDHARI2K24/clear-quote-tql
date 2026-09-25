"""AC3: `provider_tax_rates`, `provider_rents`, `provider_str_revenue`,
`provider_rate_sheet` and `provider_listings` each have at least one row per
persona market, and CQ-009's mock adapters return a non-empty result for
every persona.

Scoping note (Decision, plan.md): `MockPricingClient.get_priced_products`
is not exercised here -- building a fully valid `PricingRequestDTO` means
computing OB-derived fields (LTV, base/total loan amount, DSCR bucket, ...),
which is `pricing.enrichment.scenarios/ob_request.py::build_ob_search_request`,
CQ-013's owned logic (CQ-011 spec.md "Contracts"). Duplicating that here to
satisfy this test would be exactly the "fake CQ-013's behaviour" the
orchestrator's plan rules out; `provider_rate_sheet`'s row-count check below
still covers this item's own AC3 obligation (at least one row exists).
`MockCrmClient` is write-only (no "not found" failure mode) so it always
returns a non-empty ack; included for completeness. `MockPropertySearchClient`
is scoped to the 7 investment personas -- its own `MatchStrategy` schema
has no `PRIMARY` member, so a primary-occupancy persona has no valid search
request to build in the first place.
"""

from decimal import Decimal

from sqlalchemy import func, select

from app.integrations.credit.mock import MockCreditClient
from app.integrations.credit.models import CreditPullType
from app.integrations.crm.mock import MockCrmClient
from app.integrations.insurance.mock import MockInsuranceClient
from app.integrations.los.mock import MockLosClient
from app.integrations.pricing.models import ProviderRateSheet
from app.integrations.property_search.mock import MockPropertySearchClient
from app.integrations.property_search.models import ProviderListing
from app.integrations.property_search.schemas import MatchStrategy, PropertySearchRequestDTO
from app.integrations.rent.mock import MockRentClient
from app.integrations.rent.models import ProviderRent
from app.integrations.str.mock import MockStrClient
from app.integrations.str.models import ProviderStrRevenue
from app.integrations.tax.mock import MockTaxClient
from app.integrations.tax.models import ProviderTaxRate
from seed.tests.conftest import SeededBase


async def test_named_provider_tables_have_a_row_per_market(seeded_base: SeededBase) -> None:
    db = seeded_base.db
    for persona in seeded_base.personas:
        market = persona["market"]
        beds = persona["beds"] or 1

        tax_count = (
            await db.execute(
                select(func.count()).select_from(
                    select(ProviderTaxRate)
                    .where(
                        ProviderTaxRate.county == market["county"],
                        ProviderTaxRate.state == market["state"],
                    )
                    .subquery()
                )
            )
        ).scalar_one()
        assert tax_count >= 1, f"no provider_tax_rates row for {market}"

        rent_count = (
            await db.execute(
                select(func.count()).select_from(
                    select(ProviderRent)
                    .where(ProviderRent.zip == market["zip"], ProviderRent.beds == beds)
                    .subquery()
                )
            )
        ).scalar_one()
        assert rent_count >= 1, f"no provider_rents row for {market} beds={beds}"

        str_count = (
            await db.execute(
                select(func.count()).select_from(
                    select(ProviderStrRevenue)
                    .where(ProviderStrRevenue.zip == market["zip"], ProviderStrRevenue.beds == beds)
                    .subquery()
                )
            )
        ).scalar_one()
        assert str_count >= 1, f"no provider_str_revenue row for {market} beds={beds}"

        listing_count = (
            await db.execute(
                select(func.count()).select_from(
                    select(ProviderListing)
                    .where(
                        ProviderListing.state == market["state"],
                        ProviderListing.metro == market["city"],
                    )
                    .subquery()
                )
            )
        ).scalar_one()
        assert listing_count >= 1, f"no provider_listings row for {market}"

    rate_sheet_stmt = select(func.count()).select_from(ProviderRateSheet)
    rate_sheet_count = (await db.execute(rate_sheet_stmt)).scalar_one()
    assert 8 <= rate_sheet_count <= 15


async def test_los_adapter_returns_non_empty_for_every_persona(seeded_base: SeededBase) -> None:
    los_client = MockLosClient(seeded_base.db)
    for persona in seeded_base.personas:
        loan_file = await los_client.get_loan_file(persona["loan_number"])
        assert loan_file.loan_number == persona["loan_number"]
        assert loan_file.borrower_full_name


async def test_tax_adapter_returns_non_empty_for_every_persona(seeded_base: SeededBase) -> None:
    tax_client = MockTaxClient(seeded_base.db)
    for persona in seeded_base.personas:
        market = persona["market"]
        rate = await tax_client.get_tax_rate(market["state"], market["county"])
        assert rate.annual_rate_pct > 0


async def test_rent_and_str_adapters_return_non_empty_for_every_persona(
    seeded_base: SeededBase,
) -> None:
    rent_client = MockRentClient(seeded_base.db)
    str_client = MockStrClient(seeded_base.db)
    for persona in seeded_base.personas:
        market = persona["market"]
        beds = persona["beds"] or 1
        rent = await rent_client.get_market_rent(market["zip"], beds)
        assert rent.market_rent > 0
        str_rev = await str_client.get_str_revenue(market["zip"], beds)
        assert str_rev.annual_revenue > 0


async def test_credit_adapter_returns_non_empty_for_every_persona(seeded_base: SeededBase) -> None:
    credit_client = MockCreditClient(seeded_base.db)
    for persona in seeded_base.personas:
        report = await credit_client.pull_credit(persona["loan_number"], CreditPullType.SOFT_PULL)
        assert report.middle_score > 0


async def test_insurance_adapter_returns_non_empty_for_every_persona(
    seeded_base: SeededBase,
) -> None:
    insurance_client = MockInsuranceClient(seeded_base.db)
    for persona in seeded_base.personas:
        estimate = await insurance_client.get_insurance_estimate(
            persona["market"]["state"], Decimal(str(persona["purchase_price"]))
        )
        assert estimate.annual_premium > 0


async def test_property_search_adapter_returns_non_empty_for_investment_personas(
    seeded_base: SeededBase,
) -> None:
    property_search_client = MockPropertySearchClient(seeded_base.db)
    for persona in seeded_base.personas:
        if persona["occupancy"] != "investment":
            continue
        market = persona["market"]
        request = PropertySearchRequestDTO(
            approved_purchase_price=Decimal(str(persona["purchase_price"])),
            buy_box_states=[market["state"]],
            buy_box_metros=[market["city"]],
            strategy=MatchStrategy(persona["strategy"].upper()),
        )
        matches = await property_search_client.search_matches(request)
        assert len(matches) >= 1, f"no property matches for {persona['key']}"


async def test_crm_adapter_acks_for_every_persona(seeded_base: SeededBase) -> None:
    crm_client = MockCrmClient(seeded_base.db)
    for persona in seeded_base.personas:
        ack = await crm_client.log_event(persona["key"], "seed.smoke_test", {"source": "CQ-010"})
        assert ack.contact_id == persona["key"]
