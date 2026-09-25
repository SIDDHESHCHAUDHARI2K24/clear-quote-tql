"""AC2: `enrich_pricing_fields` writes `field_values` rows with the correct
`source` for tax/insurance/LTR-rent/STR-revenue/HOA and skips fields already
overridden.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FieldSource, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.verification.models import FieldValue
from app.features.pricing.enrichment.service import enrich_pricing_fields
from app.integrations.insurance.models import ProviderInsuranceFactor
from app.integrations.rent.models import ProviderRent
from app.integrations.str.models import ProviderStrRevenue
from app.integrations.tax.models import ProviderTaxRate


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


async def _seed_rent(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderRent(
            zip="28803",
            beds=1,
            market_rent=Decimal("1850.00"),
            rent_low=Decimal("1700.00"),
            rent_high=Decimal("2000.00"),
            comps_count=12,
            as_of=date(2026, 1, 1),
        )
    )
    await db_session.flush()


async def _seed_str(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderStrRevenue(
            zip="28803",
            beds=1,
            annual_revenue=Decimal("36600.00"),
            occupancy_pct=Decimal("65.00"),
            adr=Decimal("150.00"),
            comps_count=8,
            as_of=date(2026, 1, 1),
        )
    )
    await db_session.flush()


async def _field(db_session: AsyncSession, application_id: object, field_key: str) -> FieldValue:
    row = (
        await db_session.execute(
            select(FieldValue).where(
                FieldValue.application_id == application_id, FieldValue.field_key == field_key
            )
        )
    ).scalar_one()
    return row


async def test_enrich_primary_writes_tax_insurance_hoa(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    await _seed_tax(db_session)
    application = await make_application(occupancy=Occupancy.PRIMARY)

    result = await enrich_pricing_fields(db_session, application.id)

    assert set(result.field_keys_written) == {
        "property_tax_annual_rate",
        "homeowners_ins_annual",
        "hoa_fee_monthly",
    }

    tax = await _field(db_session, application.id, "property_tax_annual_rate")
    assert tax.source == FieldSource.SMARTASSET
    assert Decimal(str(tax.value)) == Decimal("0.6010") / Decimal("100")

    insurance = await _field(db_session, application.id, "homeowners_ins_annual")
    assert insurance.source == FieldSource.STEADILY
    # No seeded `provider_insurance_factors` row for NC -> falls back to the
    # mock's own 0.50% default, applied to $300,000.
    assert Decimal(str(insurance.value)) == Decimal("1500.00")

    hoa = await _field(db_session, application.id, "hoa_fee_monthly")
    assert hoa.source == FieldSource.DEFAULT
    assert Decimal(str(hoa.value)) == Decimal("0.00")

    # Primary never gets rent/STR fields.
    rent = (
        await db_session.execute(
            select(FieldValue).where(
                FieldValue.application_id == application.id,
                FieldValue.field_key == "market_rent_ltr",
            )
        )
    ).scalar_one_or_none()
    assert rent is None


async def test_enrich_investment_ltr_writes_market_rent(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    await _seed_tax(db_session)
    await _seed_rent(db_session)
    application = await make_application(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)

    result = await enrich_pricing_fields(db_session, application.id)

    assert "market_rent_ltr" in result.field_keys_written
    rent = await _field(db_session, application.id, "market_rent_ltr")
    assert rent.source == FieldSource.RENTCAST
    assert Decimal(str(rent.value)) == Decimal("1850.00")


async def test_enrich_investment_str_writes_gross_revenue(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    await _seed_tax(db_session)
    await _seed_str(db_session)
    application = await make_application(occupancy=Occupancy.INVESTMENT, strategy=Strategy.STR)

    result = await enrich_pricing_fields(db_session, application.id)

    assert "gross_annual_revenue_str" in result.field_keys_written
    revenue = await _field(db_session, application.id, "gross_annual_revenue_str")
    assert revenue.source == FieldSource.AIRDNA
    assert Decimal(str(revenue.value)) == Decimal("36600.00")


async def test_enrich_uses_seeded_insurance_factor_when_present(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    await _seed_tax(db_session)
    db_session.add(
        ProviderInsuranceFactor(
            state="NC", annual_rate_pct=Decimal("0.4000"), source_name="Steadily"
        )
    )
    await db_session.flush()
    application = await make_application(occupancy=Occupancy.PRIMARY)

    await enrich_pricing_fields(db_session, application.id)

    insurance = await _field(db_session, application.id, "homeowners_ins_annual")
    assert Decimal(str(insurance.value)) == Decimal("1200.00")  # 0.40% of $300,000


async def test_enrich_skips_overridden_field(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    await _seed_tax(db_session)
    application = await make_application(occupancy=Occupancy.PRIMARY)

    overridden = FieldValue(
        application_id=application.id,
        field_key="property_tax_annual_rate",
        value="0.0123",
        source=FieldSource.LO_OVERRIDE,
        overridden_by=application.lo_id,
        overridden_at=datetime.now(UTC),
    )
    db_session.add(overridden)
    await db_session.flush()

    result = await enrich_pricing_fields(db_session, application.id)

    assert "property_tax_annual_rate" not in result.field_keys_written
    tax = await _field(db_session, application.id, "property_tax_annual_rate")
    assert Decimal(str(tax.value)) == Decimal("0.0123")
    assert tax.overridden_by == application.lo_id


async def test_enrich_is_idempotent_when_run_twice(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    await _seed_tax(db_session)
    application = await make_application(occupancy=Occupancy.PRIMARY)

    await enrich_pricing_fields(db_session, application.id)
    await enrich_pricing_fields(db_session, application.id)

    rows = (
        (
            await db_session.execute(
                select(FieldValue).where(
                    FieldValue.application_id == application.id,
                    FieldValue.field_key == "property_tax_annual_rate",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
