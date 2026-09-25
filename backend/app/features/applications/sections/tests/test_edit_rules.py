"""Edit rules added after code review: encrypted sensitive originals,
occupancy/strategy coupling, required housing state/zip, and the timeline
entry when a resume call fails."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Occupancy, Strategy
from app.features.applications.models import Application
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
