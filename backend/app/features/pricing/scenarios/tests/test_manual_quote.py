"""AC10: `POST /scenarios/{id}/quotes` (manual pick) persists a `quotes` row
with `computed` equal to `compute_quote` run on that scenario's inputs with
the picked row's rate/points."""

from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy
from app.features.applications.models import Application
from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.pricing.scenarios.dscr_loop import inputs_with_priced_product
from app.features.pricing.scenarios.service import create_scenario
from app.integrations.pricing.schemas import PricedProductDTO

_PRODUCT = {
    "investor_name": "Rocket Pro",
    "product_name": "Conventional 30 Yr Fixed",
    "lock_period_days": 30,
    "note_rate": "7.250",
    "price_pct": "100.500",
    "discount_points_pct": "-0.005",
    "discount_points_amount": "-1200.00",
    "is_par_rate": False,
    "is_buydown_rate": False,
}


async def test_manual_quote_computed_matches_compute_quote(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await make_application(
        occupancy=Occupancy.PRIMARY, requested_price=Decimal("300000.00")
    )
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await db_session.commit()

    scenario = await create_scenario(
        db_session, application.id, Decimal("300000.00"), Decimal("0.20"), StrategyType.PRIMARY
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/scenarios/{scenario.id}/quotes",
        json={"product": _PRODUCT, "label": "Manual"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "Manual"
    assert body["investor"] == "Rocket Pro"
    assert Decimal(body["rate"]) == Decimal("7.250")

    base_inputs = ScenarioInputs.model_validate(scenario.inputs)
    config = ConfigSnapshot.model_validate(scenario.config_snapshot)
    product = PricedProductDTO.model_validate(_PRODUCT)
    expected = compute_quote(inputs_with_priced_product(base_inputs, product), config)

    assert Decimal(body["computed"]["cash_to_close"]) == expected.cash_to_close
    assert Decimal(body["computed"]["monthly_pi"]) == expected.monthly_pi
    assert Decimal(body["computed"]["loan_amount"]) == expected.loan_amount
