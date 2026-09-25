"""Section reads: masked SSN, flags, tab summaries, DTI/income gating (AC8)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import PropertyAddressStatus
from app.features.applications.sections import service as section_service
from app.features.applications.verification.schemas import ScenarioSnapshot
from app.features.applications.verification.service import write_flag
from conftest import StaffSession

MakeApp = Callable[..., Awaitable[Application]]


def _field(section: dict[str, Any], field_key: str) -> dict[str, Any]:
    for record in section["records"]:
        for field in record["fields"]:
            if field["field_key"] == field_key:
                return field
    raise AssertionError(f"{field_key} not in section")


def _priced(monkeypatch: pytest.MonkeyPatch, payment: str, ctc: str) -> None:
    async def _snapshot(*_args: object) -> ScenarioSnapshot:
        return ScenarioSnapshot(
            total_cash_to_close=Decimal(ctc), total_monthly_payment=Decimal(payment)
        )

    monkeypatch.setattr(section_service, "latest_scenario_snapshot", _snapshot)


async def test_borrowers_section_masks_ssn(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(ssn="123456789", co_borrower=True)

    response = await client.get(f"/api/v1/applications/{app.id}/sections/borrowers")

    assert response.status_code == 200
    body = response.json()
    assert "123456789" not in response.text
    assert _field(body, "borrower_ssn")["value"] == "***-**-6789"
    assert _field(body, "co_borrower_ssn")["value"] == "***-**-4321"
    roles = [r["role"] for r in body["records"] if r["kind"] == "party"]
    assert roles == ["borrower", "co_borrower"]
    cell = _field(body, "borrower_cell_phone")
    assert cell["source"] == "encompass"
    assert cell["overridden"] is False
    # Auto-copied by phone_copy at import (home phone was empty in the LOS).
    assert _field(body, "borrower_home_phone")["source"] == "formula"


async def test_section_404_for_other_lo(
    client: AsyncClient,
    make_app: MakeApp,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    app = await make_app()
    await make_staff_session(role=UserRole.LO)

    response = await client.get(f"/api/v1/applications/{app.id}/sections/borrowers")

    assert response.status_code == 404


async def test_housing_summary_and_flag(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(housing=[(1, 2)])

    body = (await client.get(f"/api/v1/applications/{app.id}/sections/housing")).json()

    assert body["housing"] == {
        "total_months": 14,
        "required_months": 24,
        "meets_requirement": False,
    }
    [flag] = body["flags"]
    assert flag["rule"] == "housing_history_24mo"
    assert flag["severity"] == "blocking"
    assert "14 months" in flag["message"]


async def test_credit_summary_fico_and_pull(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(fico=742)

    body = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()

    credit = body["credit"]
    assert credit["representative_fico"] == 742
    assert credit["fico_bracket"] == "740–759"
    assert credit["pull_type"] == "soft_pull"
    assert credit["pulled_at"] is not None
    assert credit["consent"] is None
    assert Decimal(credit["liabilities_monthly_total"]) == Decimal("300.00")
    assert [r["kind"] for r in body["records"]] == ["credit", "liability"]


async def test_dti_primary_only(
    client: AsyncClient, make_app: MakeApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _priced(monkeypatch, payment="1500.00", ctc="70000.00")
    primary = await make_app(occupancy=Occupancy.PRIMARY, monthly_income="6000.00")
    investment = await make_app(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)

    p = (await client.get(f"/api/v1/applications/{primary.id}/sections/credit")).json()
    i = (await client.get(f"/api/v1/applications/{investment.id}/sections/credit")).json()

    assert p["credit"]["dti_applicable"] is True
    assert p["credit"]["dti_status"] == "ok"
    # (300 liabilities + 1500 payment) / 6000 income
    assert Decimal(p["credit"]["dti"]) == Decimal("0.3000")
    assert i["credit"]["dti_applicable"] is False
    assert i["credit"]["dti"] is None
    assert i["credit"]["dti_status"] == "not_applicable"


async def test_dti_awaiting_pricing_without_quote(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(occupancy=Occupancy.PRIMARY)

    body = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()

    assert body["credit"]["dti"] is None
    assert body["credit"]["dti_status"] == "awaiting_pricing"


async def test_assets_employment_primary_only(
    client: AsyncClient, make_app: MakeApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _priced(monkeypatch, payment="1500.00", ctc="70000.00")
    primary = await make_app(occupancy=Occupancy.PRIMARY, assets="80000.00")
    investment = await make_app(
        occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR, assets="75000.00"
    )

    p = (await client.get(f"/api/v1/applications/{primary.id}/sections/assets")).json()
    i = (await client.get(f"/api/v1/applications/{investment.id}/sections/assets")).json()

    assert "employment" in [r["kind"] for r in p["records"]]
    assert p["assets"]["income_applicable"] is True
    assert Decimal(p["assets"]["monthly_income_total"]) == Decimal("9000.00")
    # Primary: 2 months reserves -> 70000 + 3000 = 73000 <= 80000.
    assert Decimal(p["assets"]["reserves_required"]) == Decimal("3000.00")
    assert p["assets"]["status"] == "sufficient"

    assert "employment" not in [r["kind"] for r in i["records"]]
    assert i["assets"]["income_applicable"] is False
    assert i["assets"]["monthly_income_total"] is None
    # Investment: 6 months PITIA -> 70000 + 9000 = 79000 > 75000.
    assert i["assets"]["reserves_months"] == 6
    assert Decimal(i["assets"]["reserves_required"]) == Decimal("9000.00")
    assert Decimal(i["assets"]["required_funds"]) == Decimal("79000.00")
    assert i["assets"]["status"] == "insufficient"


async def test_property_section_tbd(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(address_status=PropertyAddressStatus.TBD, state="FL")

    body = (await client.get(f"/api/v1/applications/{app.id}/sections/property")).json()

    assert body["property"]["tbd"] is True
    assert body["property"]["recommend_matches"] is True
    assert body["property"]["buy_box_states"] == ["FL"]
    assert _field(body, "occupancy_type")["value"] == "primary"


async def test_property_section_lists_occupancy_flag(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    """Aisha's pricing-tab flag shows on the tab that edits the field."""
    app = await make_app(occupancy=None, strategy=Strategy.LTR)
    await write_flag(
        db_session,
        app.id,
        ApplicationTab.PRICING,
        "occupancy_type",
        "ob_required_field",
        FlagSeverity.BLOCKING,
    )
    await db_session.commit()

    body = (await client.get(f"/api/v1/applications/{app.id}/sections/property")).json()

    assert [f["field_key"] for f in body["flags"]] == ["occupancy_type"]
    assert body["flags"][0]["message"] == "Cannot price: missing Occupancy"
