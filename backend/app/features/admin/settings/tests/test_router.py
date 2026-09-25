"""spec.md AC6: `GET /admin/settings` -- admin-only, every documented
key present with its source, and the values equal the `ConfigSnapshot`
stored on a newly created scenario (plan.md decision 7)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.settings.tests.test_defaults import EXPECTED as SETTINGS_TABLE_DEFAULTS
from conftest import StaffSession

# `settings` key -> `ConfigSnapshot` field, for every key the two share
# (plan.md decision 7). `stale_quote_days`/`report_link_expiry_days` are
# settings-table-only (not part of the pricing config); the two
# `default_down_payment_*` keys are `ConfigSnapshot`-absent code defaults,
# checked separately below.
_SNAPSHOT_FIELD_BY_SETTINGS_KEY = {
    "fee_lender_processing": "lender_processing_fee",
    "fee_lender_underwriting": "lender_underwriting_fee",
    "title_pct": "title_rate_pct",
    "str_expense_ratio": "str_expense_ratio",
    "insurance_default_pct": "insurance_rate_pct",
    "land_allocation_pct": "land_allocation_pct",
    "accelerated_property_pct": "accelerated_property_pct",
    "bonus_depreciation_pct": "bonus_depreciation_pct",
    "investor_marginal_tax_rate": "investor_marginal_tax_rate",
    "prepaid_interest_days": "prepaid_interest_days",
    "prepaid_insurance_months": "prepaid_insurance_months",
    "prepaid_tax_months": "prepaid_tax_months",
    "reserves_months_primary": "reserves_months_primary",
    "reserves_months_investment": "reserves_months_investment",
}


async def test_settings_401_without_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/settings")
    assert response.status_code == 401


async def test_settings_admin_only(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await make_staff_session(role=UserRole.LO)
    assert (await client.get("/api/v1/admin/settings")).status_code == 403

    await make_staff_session(role=UserRole.ADMIN)
    assert (await client.get("/api/v1/admin/settings")).status_code == 200


async def test_settings_lists_every_documented_key(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await make_staff_session(role=UserRole.ADMIN)
    response = await client.get("/api/v1/admin/settings")
    by_key = {row["key"]: row for row in response.json()["settings"]}

    for key, expected_value in SETTINGS_TABLE_DEFAULTS.items():
        assert by_key[key]["source"] == "settings_table"
        assert float(by_key[key]["value"]) == float(expected_value)

    for key in ("default_down_payment_primary_pct", "default_down_payment_investment_pct"):
        assert by_key[key]["source"] == "code_default"


async def test_settings_match_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC6: builds a scenario the same way `create_scenario`/`auto_price`
    persist one (`config = ConfigSnapshot()`, `inputs.down_payment_pct` =
    the primary default) and checks the settings page's values against it."""
    owner = await make_staff_session(role=UserRole.ADMIN)
    application = await make_application(lo=owner.user)

    config = ConfigSnapshot()
    down_payment_pct = Decimal("0.20")  # `_DEFAULT_DOWN_PAYMENT_PRIMARY`
    inputs = ScenarioInputs(
        purchase_price=Decimal("300000.00"),
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.07"),
        strategy=StrategyType.PRIMARY,
        fico=740,
        property_tax_annual_rate=Decimal("0.012"),
        insurance_annual_rate=Decimal("0.005"),
    )
    scenario = Scenario(
        application_id=application.id,
        inputs=json.loads(inputs.model_dump_json()),
        config_snapshot=json.loads(config.model_dump_json()),
    )
    db_session.add(scenario)
    await db_session.commit()

    response = await client.get("/api/v1/admin/settings")
    by_key = {row["key"]: row["value"] for row in response.json()["settings"]}

    snapshot_json = json.loads(config.model_dump_json())
    for settings_key, snapshot_field in _SNAPSHOT_FIELD_BY_SETTINGS_KEY.items():
        assert float(by_key[settings_key]) == float(snapshot_json[snapshot_field]), settings_key

    assert float(by_key["default_down_payment_primary_pct"]) == float(down_payment_pct)
