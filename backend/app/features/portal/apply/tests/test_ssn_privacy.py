"""SSNs never sit in plaintext in `application_drafts.data` and never come
back in a response (review round 1, major 1; plan.md decision 25)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import ApplicationParty, PartyRole
from app.features.portal.apply.validation import MSG_REQUIRED, MSG_SSN
from app.integrations.property_search.models import ProviderListing

from .conftest import FakeTemporal, SentEmail

Tabs = Callable[[], dict[str, dict[str, Any]]]
BASE = "/api/v1/portal/applications"
BORROWER_SSN = "123456789"
CO_SSN = "987654321"
CO_BORROWER: dict[str, Any] = {
    "first_name": "Cody",
    "last_name": "Tampa",
    "email": "cody@example.com",
    "cell_phone": "8135550100",
    "dob": "1987-02-02",
    "ssn": "987 65 4321",
    "marital_status": "unmarried",
    "dependents_count": 1,
}


async def _raw_data(db: AsyncSession, draft_id: str) -> str:
    value: Any = (
        await db.execute(
            text("SELECT data::text FROM application_drafts WHERE id = :id"), {"id": draft_id}
        )
    ).scalar_one()
    return str(value)


def _assert_no_plain_ssn(raw: str) -> None:
    for ssn in (BORROWER_SSN, CO_SSN):
        assert ssn not in raw
        assert f"{ssn[:3]}-{ssn[3:5]}-{ssn[5:]}" not in raw
        assert f"{ssn[:3]} {ssn[3:5]} {ssn[5:]}" not in raw


def _assert_masked(you: dict[str, Any], last4: str) -> None:
    assert "ssn" not in you
    assert "ssn_encrypted" not in you
    assert you["ssn_last4"] == last4
    assert you["ssn_set"] is True


async def _patch(client: AsyncClient, draft_id: str, tab: str, data: dict[str, Any]) -> Any:
    response = await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": tab, "data": data})
    assert response.status_code == 200, response.json()
    return response.json()


async def test_ssn_is_encrypted_in_the_draft_and_masked_in_responses(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    tabs = valid_tabs()
    tabs["you"]["has_co_borrower"] = True
    tabs["you"]["co_borrower"] = dict(CO_BORROWER)

    body = await _patch(client, draft_id, "you", tabs["you"])
    assert body["tab_valid"] is True, body
    _assert_masked(body["draft"]["data"]["you"], "6789")
    _assert_masked(body["draft"]["data"]["you"]["co_borrower"], "4321")
    _assert_no_plain_ssn(str(body))
    _assert_no_plain_ssn(await _raw_data(db_session, draft_id))

    fetched = (await client.get(f"{BASE}/{draft_id}")).json()
    _assert_masked(fetched["data"]["you"], "6789")
    _assert_masked(fetched["data"]["you"]["co_borrower"], "4321")
    _assert_no_plain_ssn(str(fetched))

    # Resave without the SSNs (what the UI does once they are stored):
    # the stored ciphertext is kept and the tab still validates.
    resave = dict(tabs["you"])
    resave.pop("ssn")
    resave["co_borrower"] = {k: v for k, v in CO_BORROWER.items() if k != "ssn"} | {"ssn": ""}
    body = await _patch(client, draft_id, "you", resave)
    assert body["tab_valid"] is True, body
    _assert_masked(body["draft"]["data"]["you"], "6789")
    _assert_masked(body["draft"]["data"]["you"]["co_borrower"], "4321")

    # A client cannot plant its own ciphertext or last-4.
    forged = resave | {"ssn_encrypted": "forged", "ssn_last4": "0000", "ssn_set": False}
    body = await _patch(client, draft_id, "you", forged)
    _assert_masked(body["draft"]["data"]["you"], "6789")

    for tab in ("property", "income", "consent"):
        await _patch(client, draft_id, tab, tabs[tab])
    submitted = await client.post(f"{BASE}/{draft_id}/submit")
    assert submitted.status_code == 200, submitted.json()
    app_id = uuid.UUID(submitted.json()["application_id"])

    parties = {
        p.role: p
        for p in (
            await db_session.execute(
                select(ApplicationParty).where(ApplicationParty.application_id == app_id)
            )
        )
        .scalars()
        .all()
    }
    assert parties[PartyRole.BORROWER].ssn_encrypted == BORROWER_SSN
    assert parties[PartyRole.CO_BORROWER].ssn_encrypted == CO_SSN

    # Submit scrubs the ciphertext from the closed draft; last-4 stays.
    raw = await _raw_data(db_session, draft_id)
    _assert_no_plain_ssn(raw)
    assert "ssn_encrypted" not in raw
    closed = (await client.get(f"{BASE}/{draft_id}")).json()
    assert closed["data"]["you"]["ssn_last4"] == "6789"
    assert "ssn_encrypted" not in closed["data"]["you"]


async def test_missing_or_invalid_ssn_is_reported_not_stored(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    you = valid_tabs()["you"]

    no_ssn = {k: v for k, v in you.items() if k != "ssn"}
    body = await _patch(client, draft_id, "you", no_ssn)
    assert body["field_errors"] == {"ssn": MSG_REQUIRED}
    assert body["draft"]["data"]["you"]["ssn_set"] is False
    assert "ssn_last4" not in body["draft"]["data"]["you"]

    body = await _patch(client, draft_id, "you", you | {"ssn": "12345"})
    assert body["tab_valid"] is False
    assert body["field_errors"] == {"ssn": MSG_SSN}
    assert "12345" not in await _raw_data(db_session, draft_id)

    body = await _patch(client, draft_id, "you", you)
    assert body["tab_valid"] is True
    # A later invalid SSN replaces (clears) the stored one: never a stale
    # SSN silently kept behind an error.
    body = await _patch(client, draft_id, "you", you | {"ssn": "12-34"})
    assert body["field_errors"] == {"ssn": MSG_SSN}
    assert body["draft"]["data"]["you"]["ssn_set"] is False
    assert body["draft"]["tabs"]["you"]["complete"] is False
