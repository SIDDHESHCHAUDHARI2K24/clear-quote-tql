"""spec.md AC6: `GET /admin/settings` -- admin-only, every documented
key present with its source, and the values equal the `ConfigSnapshot`
stored on a newly created scenario (plan.md decision 7)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.service import create_default_scenarios
from app.features.settings.tests.test_defaults import EXPECTED as SETTINGS_TABLE_DEFAULTS
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram
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


def _seed_conventional_curve(db_session: AsyncSession) -> None:
    offsets = [
        Decimal("-0.250"),
        Decimal("-0.125"),
        Decimal("0.000"),
        Decimal("0.125"),
        Decimal("0.250"),
    ]
    for index, offset in enumerate(offsets):
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


def _seed_dscr_curve(db_session: AsyncSession) -> None:
    offsets = [
        Decimal("-0.250"),
        Decimal("-0.125"),
        Decimal("0.000"),
        Decimal("0.125"),
        Decimal("0.250"),
    ]
    for index, offset in enumerate(offsets):
        db_session.add(
            ProviderRateSheet(
                investor_name=f"DSCR Investor {index}",
                product_name="DSCR 30 Yr Fixed",
                program=RateSheetProgram.DSCR,
                base_rate=Decimal("7.500") + offset,
                base_price=Decimal("100.000") - offset * Decimal("4"),
                min_fico=680,
                max_ltv=Decimal("80.00"),
                dscr_bucket="ONE_TO_1_25",
                lock_days=30,
                active=True,
            )
        )


async def _match_snapshot_against_settings(
    client: AsyncClient,
    db_session: AsyncSession,
    scenario_id: object,
    *,
    down_payment_key: str,
) -> None:
    """AC6's actual assertion, shared by the primary and investment cases
    below: the settings page's values equal the `config_snapshot`/
    `inputs.down_payment_pct` persisted on a scenario the real
    `create_default_scenarios` service just built."""
    scenario = await db_session.get(Scenario, scenario_id)
    assert scenario is not None
    assert isinstance(scenario.config_snapshot, dict)
    assert isinstance(scenario.inputs, dict)

    response = await client.get("/api/v1/admin/settings")
    by_key = {row["key"]: row["value"] for row in response.json()["settings"]}

    for settings_key, snapshot_field in _SNAPSHOT_FIELD_BY_SETTINGS_KEY.items():
        assert float(by_key[settings_key]) == float(scenario.config_snapshot[snapshot_field]), (
            settings_key
        )

    assert float(by_key[down_payment_key]) == float(scenario.inputs["down_payment_pct"])


async def test_settings_match_snapshot_primary(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC6, primary: builds a scenario through the real
    `create_default_scenarios` service call (not a hand-assembled
    `Scenario` row -- code review round 1, minor 2) and checks the settings
    page's values against the persisted `config_snapshot` and the primary
    down-payment default (0.20 -- `DEFAULT_DOWN_PAYMENT_PRIMARY`)."""
    await make_staff_session(role=UserRole.ADMIN)
    application = await make_application(occupancy=Occupancy.PRIMARY)
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    _seed_conventional_curve(db_session)
    await db_session.commit()

    result = await create_default_scenarios(db_session, application.id)

    await _match_snapshot_against_settings(
        client,
        db_session,
        result.groups[0].scenario_id,
        down_payment_key="default_down_payment_primary_pct",
    )


async def test_settings_match_snapshot_investment(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC6, investment: same as the primary case above but for an
    investment (LTR) application, against the investment down-payment
    default (0.25 -- `DEFAULT_DOWN_PAYMENT_INVESTMENT`)."""
    await make_staff_session(role=UserRole.ADMIN)
    application = await make_application(
        occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR, requested_price=Decimal("342000.00")
    )
    await set_field_value(application.id, "representative_fico", Decimal("740"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2440.00"))
    _seed_dscr_curve(db_session)
    await db_session.commit()

    result = await create_default_scenarios(db_session, application.id)

    await _match_snapshot_against_settings(
        client,
        db_session,
        result.groups[0].scenario_id,
        down_payment_key="default_down_payment_investment_pct",
    )
