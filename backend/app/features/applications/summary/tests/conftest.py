"""Local fixtures for `applications/summary/tests/`: the minimum row graph
(`users -> clients -> applications`, plus optional `properties`/
`scenarios`/`quotes`/`flags`) the summary service/router tests need,
following the established per-subpackage `make_application` pattern (see
`applications/verification/tests/conftest.py`, `applications/tests/
conftest.py`)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.applications.verification.models import Flag
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.pricing.engine.types import ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(lo: User | None = None, **overrides: object) -> Application:
        if lo is None:
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

        defaults: dict[str, object] = {"occupancy": Occupancy.PRIMARY, "program": "Conventional"}
        defaults.update(overrides)
        application = Application(client_id=client.id, lo_id=lo.id, **defaults)
        db_session.add(application)
        await db_session.flush()
        return application

    return _make


@pytest_asyncio.fixture
async def make_property(db_session: AsyncSession) -> Callable[..., Awaitable[Property]]:
    async def _make(
        application: Application,
        city: str = "Columbus",
        state: str = "OH",
        zip_code: str = "43215",
    ) -> Property:
        property_row = Property(
            application_id=application.id,
            address_status=PropertyAddressStatus.SPECIFIC_ADDRESS,
            city=city,
            state=state,
            zip=zip_code,
            property_type=PropertyType.SINGLE_FAMILY,
        )
        db_session.add(property_row)
        await db_session.flush()
        return property_row

    return _make


@pytest_asyncio.fixture
async def make_flag(db_session: AsyncSession) -> Callable[..., Awaitable[Flag]]:
    async def _make(
        application: Application,
        tab: ApplicationTab,
        field_key: str = "some_field",
        rule: str = "some_rule",
        severity: FlagSeverity = FlagSeverity.BLOCKING,
        resolved: bool = False,
    ) -> Flag:
        flag = Flag(
            application_id=application.id,
            tab=tab,
            field_key=field_key,
            rule=rule,
            severity=severity,
            resolved_at=datetime.now(UTC) if resolved else None,
        )
        db_session.add(flag)
        await db_session.flush()
        return flag

    return _make


@pytest_asyncio.fixture
async def make_scenario(db_session: AsyncSession) -> Callable[..., Awaitable[Scenario]]:
    async def _make(
        application: Application,
        purchase_price: Decimal = Decimal("300000.00"),
        down_payment_pct: Decimal = Decimal("0.20"),
        strategy: StrategyType = StrategyType.PRIMARY,
        ppp_years: int | None = None,
    ) -> Scenario:
        market_rent_ltr = Decimal("2500.00") if strategy is StrategyType.LTR else None
        str_gross_annual_revenue = Decimal("48000.00") if strategy is StrategyType.STR else None
        inputs = ScenarioInputs(
            purchase_price=purchase_price,
            down_payment_pct=down_payment_pct,
            note_rate=Decimal("0.07"),
            strategy=strategy,
            fico=740,
            property_tax_annual_rate=Decimal("0.012"),
            insurance_annual_rate=Decimal("0.005"),
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
            priced_at=datetime.now(UTC),
        )
        db_session.add(quote)
        await db_session.flush()
        return quote

    return _make
