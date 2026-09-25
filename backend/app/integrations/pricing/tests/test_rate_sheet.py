"""AC7: against a seeded DSCR rate sheet, a fully valid investment request
returns 8-15 rows sorted ascending by `note_rate`, with exactly one
`is_par_rate = true` row."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.pricing.mock import MockPricingClient
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram
from app.integrations.pricing.schemas import PricingRequestDTO

# (base_rate, base_price) -- a realistic no-point-adjustment curve where the
# 7.000 row prices exactly at par (100.000).
_RATE_PRICE_PAIRS = [
    (Decimal("6.500"), Decimal("96.500")),
    (Decimal("6.625"), Decimal("97.375")),
    (Decimal("6.750"), Decimal("98.250")),
    (Decimal("6.875"), Decimal("99.125")),
    (Decimal("7.000"), Decimal("100.000")),
    (Decimal("7.125"), Decimal("100.750")),
    (Decimal("7.250"), Decimal("101.375")),
    (Decimal("7.375"), Decimal("101.875")),
    (Decimal("7.500"), Decimal("102.250")),
    (Decimal("7.625"), Decimal("102.500")),
]


def _seed_dscr_rate_sheet(session: AsyncSession) -> None:
    for index, (rate, price) in enumerate(_RATE_PRICE_PAIRS):
        session.add(
            ProviderRateSheet(
                investor_name=f"Investor {index}",
                product_name="DSCR 30 Yr Fixed",
                program=RateSheetProgram.DSCR,
                base_rate=rate,
                base_price=price,
                min_fico=680,
                max_ltv=Decimal("80.00"),
                dscr_bucket="ONE_TO_1_25",
                ppp_years=None,
                str_only=False,
                lead_source=None,
                lock_days=30,
                fico_adjustment_bps=Decimal("0"),
                ltv_adjustment_bps=Decimal("0"),
                active=True,
            )
        )


def _investment_request() -> PricingRequestDTO:
    return PricingRequestDTO(
        LoanPosition="First",
        LoanType="Non-Conforming",
        LoanPurpose="Purchase",
        BaseLoanAmount=Decimal("225000.00"),
        TotalLoanAmount=Decimal("225000.00"),
        PurchasePrice=Decimal("300000.00"),
        AppraisedValue=Decimal("300000.00"),
        LTV=Decimal("75.00"),
        CLTV=Decimal("75.00"),
        HCLTV=Decimal("75.00"),
        RepresentativeFICO=740,
        Occupancy="InvestmentProperty",
        PropertyType="SingleFamily",
        NumberOfUnits=1,
        State="NC",
        County="Buncombe",
        ZipCode="28803",
        AmortizationType="Fixed",
        AmortizationTerm=360,
        PrepaymentPenalty="5 Years",
        IncomeVerificationType="Investor - DSCR",
        DSCR=Decimal("1.10"),
        ShortTermRental="No",
        DesiredLockDays=30,
    )


async def test_valid_investment_request_returns_sorted_grid_with_one_par_row(
    db_session: AsyncSession,
) -> None:
    _seed_dscr_rate_sheet(db_session)
    await db_session.commit()

    products = await MockPricingClient(db_session).get_priced_products(_investment_request())

    assert 8 <= len(products) <= 15

    note_rates = [product.note_rate for product in products]
    assert note_rates == sorted(note_rates)

    par_rows = [product for product in products if product.is_par_rate]
    assert len(par_rows) == 1
    assert par_rows[0].price_pct == Decimal("100.000")


async def test_rows_outside_fico_ltv_or_bucket_are_excluded(db_session: AsyncSession) -> None:
    _seed_dscr_rate_sheet(db_session)
    # A conventional-program row must never show up in a DSCR result.
    db_session.add(
        ProviderRateSheet(
            investor_name="Conventional Investor",
            product_name="Conventional 30 Yr Fixed",
            program=RateSheetProgram.CONVENTIONAL,
            base_rate=Decimal("6.000"),
            base_price=Decimal("100.000"),
            min_fico=680,
            max_ltv=Decimal("80.00"),
            lock_days=30,
            fico_adjustment_bps=Decimal("0"),
            ltv_adjustment_bps=Decimal("0"),
            active=True,
        )
    )
    # A too-high min_fico row must be excluded from a 740-FICO request.
    db_session.add(
        ProviderRateSheet(
            investor_name="High FICO Only",
            product_name="DSCR 30 Yr Fixed",
            program=RateSheetProgram.DSCR,
            base_rate=Decimal("6.250"),
            base_price=Decimal("100.500"),
            min_fico=760,
            max_ltv=Decimal("80.00"),
            dscr_bucket="ONE_TO_1_25",
            lock_days=30,
            fico_adjustment_bps=Decimal("0"),
            ltv_adjustment_bps=Decimal("0"),
            active=True,
        )
    )
    await db_session.commit()

    products = await MockPricingClient(db_session).get_priced_products(_investment_request())

    assert len(products) == len(_RATE_PRICE_PAIRS)
    assert all(product.note_rate != Decimal("6.000") for product in products)
    assert all(product.note_rate != Decimal("6.250") for product in products)
