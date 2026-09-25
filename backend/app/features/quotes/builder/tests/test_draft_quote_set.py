"""`draft_default_quote_set`: confirms every quote id `auto_price`'s
`PricingResult` names belongs to the application and returns them as the
drafted set (plan.md Decision 11 -- no new persisted table in this item's
scope)."""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FieldSource, Occupancy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.pricing.scenarios.service import auto_price
from app.features.quotes.builder.service import draft_default_quote_set
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram


async def _make_primary_application(db_session: AsyncSession) -> Application:
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
        password_hash="not-a-real-hash",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()

    client = Client(
        full_name="Test Client",
        email=f"client-{uuid.uuid4()}@clearquote-demo.test",
        assigned_lo_id=lo.id,
    )
    db_session.add(client)
    await db_session.flush()

    application = Application(
        client_id=client.id,
        lo_id=lo.id,
        occupancy=Occupancy.PRIMARY,
        requested_price=Decimal("300000.00"),
    )
    db_session.add(application)
    await db_session.flush()

    db_session.add(
        Property(
            application_id=application.id,
            address_status=PropertyAddressStatus.SPECIFIC_ADDRESS,
            state="NC",
            county="Buncombe",
            zip="28803",
            property_type=PropertyType.SINGLE_FAMILY,
            number_of_units=1,
        )
    )
    db_session.add(
        FieldValue(
            application_id=application.id,
            field_key="representative_fico",
            value="760",
            source=FieldSource.LO_ENTRY,
        )
    )
    db_session.add(
        FieldValue(
            application_id=application.id,
            field_key="property_tax_annual_rate",
            value="0.01",
            source=FieldSource.LO_ENTRY,
        )
    )
    db_session.add(
        FieldValue(
            application_id=application.id,
            field_key="homeowners_ins_annual",
            value="1500.00",
            source=FieldSource.LO_ENTRY,
        )
    )
    await db_session.flush()
    return application


def _seed_conventional_rate_sheet(db_session: AsyncSession) -> None:
    for index, offset in enumerate([Decimal("-0.25"), Decimal("0.00"), Decimal("0.25")]):
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


async def test_draft_quote_set_returns_the_priced_quote_ids(db_session: AsyncSession) -> None:
    application = await _make_primary_application(db_session)
    _seed_conventional_rate_sheet(db_session)
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    assert pricing_result.quote_ids  # sanity: auto_price actually priced something

    result = await draft_default_quote_set(db_session, application.id, pricing_result)

    assert set(result.quote_ids) == set(pricing_result.quote_ids)


async def test_draft_quote_set_empty_pricing_result_is_a_noop(db_session: AsyncSession) -> None:
    application = await _make_primary_application(db_session)
    await db_session.commit()

    from app.features.pricing.scenarios.service import PricingResult

    result = await draft_default_quote_set(
        db_session, application.id, PricingResult(scenario_ids=[], quote_ids=[])
    )

    assert result.quote_ids == []
