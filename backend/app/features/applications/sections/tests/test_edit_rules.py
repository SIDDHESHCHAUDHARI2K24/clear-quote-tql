"""Edit rules added after code review: encrypted sensitive originals,
occupancy/strategy coupling, required housing state/zip, and the timeline
entry when a resume call fails."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Occupancy, Strategy
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.sections.tests.conftest import FakeHandle, FakeTemporal
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from app.workflows.constants import application_workflow_id

MakeApp = Callable[..., Awaitable[Application]]


def _field(section: dict[str, Any], field_key: str) -> dict[str, Any]:
    for record in section["records"]:
        for field in record["fields"]:
            if field["field_key"] == field_key:
                return field
    raise AssertionError(f"{field_key} not in section")


async def test_sensitive_original_is_encrypted_and_revert_restores(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app(ssn="123456789")
    url = f"/api/v1/applications/{app.id}/fields/borrower_ssn"

    await client.put(url, json={"value": "111223333"})

    stored: Any = (
        await db_session.execute(
            select(FieldValue.value).where(
                FieldValue.application_id == app.id,
                FieldValue.field_key == "orig:borrower_ssn",
            )
        )
    ).scalar_one()
    assert isinstance(stored, dict) and "enc" in stored
    assert "123456789" not in str(stored)

    body = (await client.delete(url)).json()

    assert _field(body, "borrower_ssn")["value"] == "***-**-6789"
    party_id = next(r["id"] for r in body["records"] if r["kind"] == "party")
    reveal = await client.post(f"/api/v1/applications/{app.id}/parties/{party_id}/ssn-reveal")
    assert reveal.json()["ssn"] == "123456789"


async def test_occupancy_strategy_coupling(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)
    base = f"/api/v1/applications/{app.id}/fields"

    body = (await client.put(f"{base}/occupancy_type", json={"value": "primary"})).json()
    assert _field(body, "investment_strategy")["value"] is None
    assert _field(body, "investment_strategy")["original_value"] == "ltr"

    rejected = await client.put(f"{base}/investment_strategy", json={"value": "str"})
    assert rejected.status_code == 422

    body = (await client.put(f"{base}/occupancy_type", json={"value": "investment"})).json()
    assert _field(body, "investment_strategy")["value"] == "ltr"
    assert _field(body, "investment_strategy")["overridden"] is False


async def test_blank_housing_state_is_422(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app()
    section = (await client.get(f"/api/v1/applications/{app.id}/sections/housing")).json()
    row_id = section["records"][0]["id"]

    response = await client.patch(
        f"/api/v1/applications/{app.id}/housing_history/{row_id}", json={"state": ""}
    )

    assert response.status_code == 422


async def test_resume_failure_is_logged(
    client: AsyncClient,
    make_app: MakeApp,
    db_session: AsyncSession,
    fake_temporal: FakeTemporal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    fake_temporal.running.add(application_workflow_id(str(app.id)))

    async def _boom(self: FakeHandle, _signal: Any) -> None:
        raise RuntimeError("temporal down")

    monkeypatch.setattr(FakeHandle, "signal", _boom)

    body = (
        await client.post(
            f"/api/v1/applications/{app.id}/housing_history",
            json={
                "street_address": "9 Old Rd",
                "city": "Fort Wayne",
                "state": "IN",
                "zip": "46802",
                "housing_status": "rent",
                "residence_years": 1,
                "residence_months": 0,
            },
        )
    ).json()

    assert body["resume"] == {"requested": False, "reason": "temporal_unavailable"}
    types = (
        (
            await db_session.execute(
                select(ActivityEvent.type).where(ActivityEvent.application_id == app.id)
            )
        )
        .scalars()
        .all()
    )
    assert "pipeline.resume_failed" in types
    assert uuid.UUID(body["application_id"]) == app.id


async def _primary(db: AsyncSession, application_id: uuid.UUID) -> ApplicationParty:
    return (
        await db.execute(
            select(ApplicationParty).where(
                ApplicationParty.application_id == application_id,
                ApplicationParty.role == PartyRole.BORROWER,
            )
        )
    ).scalar_one()


async def test_revert_restores_the_exact_original(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    """Review minor 1: revert converts types only; it does not re-run the
    edit parser (which strips SSN dashes and trims names)."""
    app = await make_app()
    party = await _primary(db_session, app.id)
    party.ssn_encrypted = "123-45-6789"
    party.last_name = "  Coleman "
    await db_session.commit()
    base = f"/api/v1/applications/{app.id}/fields"

    await client.put(f"{base}/borrower_ssn", json={"value": "111223333"})
    await client.put(f"{base}/borrower_last_name", json={"value": "Smith"})
    await client.put(f"{base}/borrower_dob", json={"value": "1990-03-04"})
    assert (await client.delete(f"{base}/borrower_ssn")).status_code == 200
    assert (await client.delete(f"{base}/borrower_last_name")).status_code == 200
    body = (await client.delete(f"{base}/borrower_dob")).json()

    assert _field(body, "borrower_last_name")["value"] == "  Coleman "
    assert _field(body, "borrower_dob")["value"] == "1985-01-01"
    await db_session.refresh(party)
    assert party.ssn_encrypted == "123-45-6789"
    assert party.last_name == "  Coleman "
    assert party.dob == date(1985, 1, 1)


async def test_revert_restores_typed_values(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(liabilities=[("Chase", "250.00")])
    section = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()
    row_id = next(r["id"] for r in section["records"] if r["kind"] == "liability")
    key = f"liabilities.{row_id}.monthly_payment"
    base = f"/api/v1/applications/{app.id}/fields"

    await client.put(f"{base}/{key}", json={"value": "300"})
    body = (await client.delete(f"{base}/{key}")).json()

    assert body["credit"]["liabilities_monthly_total"] == "250.00"

    await client.put(f"{base}/borrower_marital_status", json={"value": "married"})
    body = (await client.delete(f"{base}/borrower_marital_status")).json()
    assert _field(body, "borrower_marital_status")["overridden"] is False


async def test_clearing_primary_home_phone_is_rejected(
    client: AsyncClient, make_app: MakeApp
) -> None:
    """Review minor 2 (plan.md Decision #24): `phone_copy` would refill an
    empty primary home phone from the cell phone, so clearing it is a 422."""
    app = await make_app(cell_phone="2605551111", home_phone=None)
    url = f"/api/v1/applications/{app.id}/fields/borrower_home_phone"

    response = await client.put(url, json={"value": ""})

    assert response.status_code == 422
    assert "Home phone" in response.json()["error"]["message"]
    assert (await client.put(url, json={"value": "2605559999"})).status_code == 200


async def test_clearing_home_phone_allowed_without_cell(
    client: AsyncClient, make_app: MakeApp
) -> None:
    app = await make_app(cell_phone=None, home_phone="2605550000")

    response = await client.put(
        f"/api/v1/applications/{app.id}/fields/borrower_home_phone", json={"value": None}
    )

    assert response.status_code == 200
    assert _field(response.json(), "borrower_home_phone")["value"] is None


async def test_los_home_phone_equal_to_cell_does_not_follow(
    client: AsyncClient, make_app: MakeApp
) -> None:
    """Review minor 3: an LOS home phone that happens to equal the cell phone
    was not auto-copied, so a cell edit leaves it alone."""
    app = await make_app(cell_phone="2605551111", home_phone="2605551111")
    base = f"/api/v1/applications/{app.id}"
    section = (await client.get(f"{base}/sections/borrowers")).json()
    assert _field(section, "borrower_home_phone")["source"] == "encompass"

    body = (
        await client.put(f"{base}/fields/borrower_cell_phone", json={"value": "2605552222"})
    ).json()

    assert _field(body, "borrower_home_phone")["value"] == "2605551111"
    assert _field(body, "borrower_home_phone")["source"] == "encompass"


async def test_reverted_home_phone_follows_the_cell_again(
    client: AsyncClient, make_app: MakeApp
) -> None:
    app = await make_app(cell_phone="2605551111", home_phone=None)
    base = f"/api/v1/applications/{app.id}/fields"

    await client.put(f"{base}/borrower_home_phone", json={"value": "2605553333"})
    body = (await client.delete(f"{base}/borrower_home_phone")).json()
    assert _field(body, "borrower_home_phone")["value"] == "2605551111"
    assert _field(body, "borrower_home_phone")["source"] == "formula"

    body = (await client.put(f"{base}/borrower_cell_phone", json={"value": "2605554444"})).json()
    assert _field(body, "borrower_home_phone")["value"] == "2605554444"
