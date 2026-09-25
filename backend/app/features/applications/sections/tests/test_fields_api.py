"""`PUT/DELETE /fields/{field_key}`, SSN reveal, `/field-values` events
(AC3, AC7)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from conftest import StaffSession

MakeApp = Callable[..., Awaitable[Application]]


def _p(event: ActivityEvent) -> dict[str, Any]:
    assert isinstance(event.payload, dict)
    return event.payload


def _field(section: dict[str, Any], field_key: str) -> dict[str, Any]:
    for record in section["records"]:
        for field in record["fields"]:
            if field["field_key"] == field_key:
                return field
    raise AssertionError(f"{field_key} not in section")


async def _events(db: AsyncSession, application_id: uuid.UUID) -> list[ActivityEvent]:
    return list(
        (
            await db.execute(
                select(ActivityEvent)
                .where(ActivityEvent.application_id == application_id)
                .order_by(ActivityEvent.at, ActivityEvent.created_at)
            )
        )
        .scalars()
        .all()
    )


async def test_edit_audit_events(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession, staff: StaffSession
) -> None:
    app = await make_app()
    url = f"/api/v1/applications/{app.id}/fields/borrower_work_phone"

    edited = await client.put(url, json={"value": "2605559999"})

    assert edited.status_code == 200
    field = _field(edited.json(), "borrower_work_phone")
    assert field["value"] == "2605559999"
    assert field["overridden"] is True
    assert field["source"] == "lo_override"
    assert field["original_value"] is None

    reverted = await client.delete(url)

    assert reverted.status_code == 200
    field = _field(reverted.json(), "borrower_work_phone")
    assert field["value"] is None
    assert field["overridden"] is False
    assert field["source"] == "encompass"

    types = [(e.type, _p(e).get("field_key"), e.actor) for e in await _events(db_session, app.id)]
    assert ("field.edited", "borrower_work_phone", str(staff.user.id)) in types
    assert ("field.reverted", "borrower_work_phone", str(staff.user.id)) in types
    edited_event = next(e for e in await _events(db_session, app.id) if e.type == "field.edited")
    assert _p(edited_event)["message"] == "Edited Work phone"


async def test_revert_without_edit_404(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app()

    response = await client.delete(f"/api/v1/applications/{app.id}/fields/borrower_email")

    assert response.status_code == 404


async def test_row_field_edit_keeps_original(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(liabilities=[("Chase", "250.00")])
    section = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()
    liability = next(r for r in section["records"] if r["kind"] == "liability")
    key = f"liabilities.{liability['id']}.monthly_payment"

    first = await client.put(f"/api/v1/applications/{app.id}/fields/{key}", json={"value": "275"})
    second = await client.put(f"/api/v1/applications/{app.id}/fields/{key}", json={"value": "290"})

    assert first.status_code == 200
    field = _field(second.json(), key)
    assert field["value"] == "290.00"
    assert field["original_value"] == "250.00"
    assert second.json()["credit"]["liabilities_monthly_total"] == "290.00"


async def test_invalid_and_unknown_fields_422(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app()
    base = f"/api/v1/applications/{app.id}/fields"

    assert (await client.put(f"{base}/not_a_field", json={"value": "x"})).status_code == 422
    assert (await client.put(f"{base}/hoa_fee_monthly", json={"value": "1"})).status_code == 422
    bad = await client.put(f"{base}/occupancy_type", json={"value": "vacation"})
    assert bad.status_code == 422
    assert "Occupancy" in bad.json()["error"]["message"]
    missing = await client.put(f"{base}/co_borrower_email", json={"value": "a@b.c"})
    assert missing.status_code == 404


async def test_field_edit_404_for_other_lo(
    client: AsyncClient,
    make_app: MakeApp,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    app = await make_app()
    await make_staff_session(role=UserRole.LO)

    response = await client.put(
        f"/api/v1/applications/{app.id}/fields/borrower_email", json={"value": "x@y.z"}
    )

    assert response.status_code == 404


async def test_phone_copy_rule(client: AsyncClient, make_app: MakeApp) -> None:
    """AC3: an auto-copied home phone follows the cell phone; a manually
    entered one does not."""
    auto = await make_app(cell_phone="2605551111", home_phone=None)
    base = f"/api/v1/applications/{auto.id}"

    body = (
        await client.put(f"{base}/fields/borrower_cell_phone", json={"value": "2605552222"})
    ).json()

    assert _field(body, "borrower_cell_phone")["value"] == "2605552222"
    assert _field(body, "borrower_home_phone")["value"] == "2605552222"
    assert _field(body, "borrower_home_phone")["source"] == "formula"

    # The LO now types a home phone by hand; a later cell edit leaves it alone.
    await client.put(f"{base}/fields/borrower_home_phone", json={"value": "2605553333"})
    body = (
        await client.put(f"{base}/fields/borrower_cell_phone", json={"value": "2605554444"})
    ).json()

    assert _field(body, "borrower_cell_phone")["value"] == "2605554444"
    assert _field(body, "borrower_home_phone")["value"] == "2605553333"
    assert _field(body, "borrower_home_phone")["overridden"] is True

    # A home phone that came from the LOS (different number) is manual too.
    imported = await make_app(cell_phone="2605551111", home_phone="2605550000")
    body = (
        await client.put(
            f"/api/v1/applications/{imported.id}/fields/borrower_cell_phone",
            json={"value": "2605557777"},
        )
    ).json()
    assert _field(body, "borrower_home_phone")["value"] == "2605550000"


async def test_phone_rule_via_party_patch(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(cell_phone="2605551111", home_phone=None)
    section = (await client.get(f"/api/v1/applications/{app.id}/sections/borrowers")).json()
    party_id = section["records"][0]["id"]

    response = await client.patch(
        f"/api/v1/applications/{app.id}/parties/{party_id}",
        json={"cell_phone": "3175550101", "marital_status": "married"},
    )

    assert response.status_code == 200
    body = response.json()
    assert _field(body, "borrower_home_phone")["value"] == "3175550101"
    assert _field(body, "borrower_marital_status")["value"] == "married"


async def test_ssn_reveal_writes_event(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app(ssn="123456789")
    section = (await client.get(f"/api/v1/applications/{app.id}/sections/borrowers")).json()
    party_id = section["records"][0]["id"]

    response = await client.post(f"/api/v1/applications/{app.id}/parties/{party_id}/ssn-reveal")

    assert response.status_code == 200
    assert response.json() == {"party_id": party_id, "ssn": "123456789"}
    assert response.headers["cache-control"] == "no-store"
    [event] = [e for e in await _events(db_session, app.id) if e.type == "ssn.revealed"]
    assert _p(event)["field_key"] == "borrower_ssn"
    assert "123456789" not in str(_p(event))


async def test_ssn_edit_event_is_masked(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app(ssn="123456789")

    body = (
        await client.put(
            f"/api/v1/applications/{app.id}/fields/borrower_ssn", json={"value": "111-22-3333"}
        )
    ).json()

    assert _field(body, "borrower_ssn")["value"] == "***-**-3333"
    assert _field(body, "borrower_ssn")["original_value"] == "***-**-6789"
    [event] = [e for e in await _events(db_session, app.id) if e.type == "field.edited"]
    assert "111223333" not in str(_p(event))
    assert "123456789" not in str(_p(event))


async def test_field_values_routes_write_events(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    """AC7 for the pricing override/revert routes (enrichment router hook)."""
    app = await make_app()
    url = f"/api/v1/applications/{app.id}/field-values/hoa_fee_monthly"

    assert (await client.patch(url, json={"value": "125.00"})).status_code == 200
    assert (await client.post(f"{url}/revert")).status_code == 200

    types = [(e.type, _p(e).get("field_key")) for e in await _events(db_session, app.id)]
    assert ("field.edited", "hoa_fee_monthly") in types
    assert ("field.reverted", "hoa_fee_monthly") in types
    # The provenance store never collides with the pricing row.
    keys = (
        (
            await db_session.execute(
                select(FieldValue.field_key).where(FieldValue.application_id == app.id)
            )
        )
        .scalars()
        .all()
    )
    assert "hoa_fee_monthly" in keys
