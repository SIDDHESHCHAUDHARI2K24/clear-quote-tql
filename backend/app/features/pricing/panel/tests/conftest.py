"""Local fixtures for `pricing/panel/tests/`: `make_application`/
`set_field_value` come from `pricing/conftest.py` (a parent conftest, auto-
discovered); this file adds `make_scenario`/`make_quote`, following the same
shape `applications/summary/tests/conftest.py` uses (each test module owns
its own fixtures rather than importing across a feature boundary)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import Application
from app.features.pricing.engine.types import ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote


@pytest_asyncio.fixture
async def make_scenario(db_session: AsyncSession) -> Callable[..., Awaitable[Scenario]]:
    async def _make(
        application: Application,
        purchase_price: Decimal = Decimal("300000.00"),
        down_payment_pct: Decimal = Decimal("0.20"),
        strategy: StrategyType = StrategyType.PRIMARY,
        ppp_years: int | None = None,
        fico: int = 740,
        property_tax_annual_rate: Decimal = Decimal("0.012"),
        insurance_annual_rate: Decimal = Decimal("0.005"),
        market_rent_ltr: Decimal | None = None,
        str_gross_annual_revenue: Decimal | None = None,
    ) -> Scenario:
        if strategy is StrategyType.LTR and market_rent_ltr is None:
            market_rent_ltr = Decimal("2500.00")
        if strategy is StrategyType.STR and str_gross_annual_revenue is None:
            str_gross_annual_revenue = Decimal("48000.00")
        inputs = ScenarioInputs(
            purchase_price=purchase_price,
            down_payment_pct=down_payment_pct,
            note_rate=Decimal("0"),
            strategy=strategy,
            fico=fico,
            property_tax_annual_rate=property_tax_annual_rate,
            insurance_annual_rate=insurance_annual_rate,
            market_rent_ltr=market_rent_ltr,
            str_gross_annual_revenue=str_gross_annual_revenue,
        )
        inputs_json = json.loads(inputs.model_dump_json())
        if ppp_years is not None:
            inputs_json["prepayment_penalty_years"] = ppp_years
        scenario = Scenario(
            application_id=application.id,
            inputs=inputs_json,
            config_snapshot={},
        )
        db_session.add(scenario)
        await db_session.flush()
        return scenario

    return _make


@pytest_asyncio.fixture
async def make_quote(db_session: AsyncSession) -> Callable[..., Awaitable[Quote]]:
    async def _make(
        scenario: Scenario,
        rate: Decimal = Decimal("7.500"),
        label: str = "Par",
        stale: bool = False,
        priced_at: datetime | None = None,
    ) -> Quote:
        quote = Quote(
            scenario_id=scenario.id,
            investor="Mock Investor",
            product="30yr Fixed",
            rate=rate,
            points=Decimal("0.000"),
            lock_days=30,
            computed={},
            label=label,
            priced_at=priced_at or datetime.now(UTC),
            stale=stale,
        )
        db_session.add(quote)
        await db_session.flush()
        return quote

    return _make
