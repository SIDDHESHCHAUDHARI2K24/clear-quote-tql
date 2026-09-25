"""AC9: `GET /scenarios/{id}/products` returns 8-15 rows shaped per the
catalog's inbound fields."""

from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.features.applications.models import Application
from app.features.pricing.engine.types import StrategyType
from app.features.pricing.scenarios.service import create_scenario
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram
from conftest import StaffSession

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


def _seed_dscr_rate_sheet(db_session: AsyncSession, dscr_bucket: str) -> None:
    for index, (rate, price) in enumerate(_RATE_PRICE_PAIRS):
        db_session.add(
            ProviderRateSheet(
                investor_name=f"Investor {index}",
                product_name="DSCR 30 Yr Fixed",
                program=RateSheetProgram.DSCR,
                base_rate=rate,
                base_price=price,
                min_fico=680,
                max_ltv=Decimal("80.00"),
                dscr_bucket=dscr_bucket,
                lock_days=30,
                active=True,
            )
        )


async def test_products_grid_returns_8_to_15_rows(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    staff = await make_staff_session()
    application = await make_application(
        occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR, lo=staff.user
    )
    await set_field_value(application.id, "representative_fico", Decimal("740"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2440.00"))
    _seed_dscr_rate_sheet(db_session, "ONE_TO_1_25")
    _seed_dscr_rate_sheet(db_session, "GE_1_25")
    _seed_dscr_rate_sheet(db_session, "BELOW_1_00")
    await db_session.commit()

    scenario = await create_scenario(
        db_session, application.id, Decimal("300000.00"), Decimal("0.20"), StrategyType.LTR
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/scenarios/{scenario.id}/products")

    assert response.status_code == 200
    rows = response.json()
    assert 8 <= len(rows) <= 15
    for row in rows:
        assert set(row.keys()) == {
            "investor_name",
            "product_name",
            "lock_period_days",
            "note_rate",
            "price_pct",
            "discount_points_pct",
            "discount_points_amount",
            "is_par_rate",
            "is_buydown_rate",
        }
    assert sum(1 for row in rows if row["is_par_rate"]) == 1
