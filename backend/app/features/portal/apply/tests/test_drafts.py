"""Draft create/get/autosave (CQ-032 AC2, AC3; plan.md decisions 1-4)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.portal.apply.consent_text import CONSENT_TEXT, CONSENT_TEXT_VERSION
from app.features.portal.apply.models import ApplicationDraft
from app.features.portal.apply.validation import MSG_INCOME_PRIMARY, MSG_PRIOR_ADDRESS
from app.integrations.property_search.models import ProviderListing

from .conftest import PDF_BYTES, PNG_BYTES, StubS3

Tabs = Callable[[], dict[str, dict[str, Any]]]
BASE = "/api/v1/portal/applications"


async def test_requires_borrower_session(client: AsyncClient) -> None:
    response = await client.post(BASE)
    assert response.status_code == 401


async def test_create_returns_existing_open_draft(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
) -> None:
    session = await make_borrower_session()
    first = await client.post(BASE)
    assert first.status_code == 200
    body = first.json()
    assert body["email"] == session.account.email
    assert body["current_tab"] == "you"
    assert body["tabs"]["you"] == {"complete": False}
    assert body["consent"] == {"version": CONSENT_TEXT_VERSION, "text": CONSENT_TEXT}

    second = await client.post(BASE)
    assert second.json()["id"] == body["id"]
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(ApplicationDraft)
            .where(ApplicationDraft.borrower_account_id == session.account.id)
        )
    ).scalar_one()
    assert count == 1

    fetched = await client.get(f"{BASE}/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


async def test_other_borrower_gets_404(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    stub_storage: StubS3,
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    doc_id = (
        await client.post(
            f"{BASE}/{draft_id}/documents",
            files={"file": ("w2.png", PNG_BYTES, "image/png")},
            data={"doc_type": "w2"},
        )
    ).json()["id"]
    owner_keys = stub_storage.keys()

    await make_borrower_session()  # a different borrower signs in
    assert (await client.get(f"{BASE}/{draft_id}")).status_code == 404
    patch = await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": "you", "data": {}})
    assert patch.status_code == 404
    assert (await client.post(f"{BASE}/{draft_id}/submit")).status_code == 404
    upload = await client.post(
        f"{BASE}/{draft_id}/documents",
        files={"file": ("a.pdf", PDF_BYTES, "application/pdf")},
        data={"doc_type": "pay_stub"},
    )
    assert upload.status_code == 404
    assert stub_storage.keys() == owner_keys
    assert (await client.delete(f"{BASE}/{draft_id}/documents/{doc_id}")).status_code == 404
    assert len(owner_keys) == 1 and stub_storage.keys() == owner_keys


async def test_autosave_returns_field_errors_without_blocking(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
) -> None:
    """AC2 over the API: the save always lands; errors come back."""
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    tabs = valid_tabs()

    you = tabs["you"] | {"residence_years": 1, "residence_months": 2, "email": "evil@x.test"}
    response = await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": "you", "data": you})
    assert response.status_code == 200
    body = response.json()
    assert body["tab_valid"] is False
    assert body["field_errors"] == {"prior_address": MSG_PRIOR_ADDRESS}
    saved = body["draft"]["data"]["you"]
    assert saved["residence_months"] == 2
    assert "email" not in saved  # read-only: never stored from the client

    prop = tabs["property"] | {"occupancy": "primary", "down_payment_pct": "0.20"}
    await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": "property", "data": prop})
    response = await client.patch(
        f"{BASE}/{draft_id}/draft", json={"tab": "income", "data": tabs["income"]}
    )
    body = response.json()
    assert body["tab_valid"] is False
    assert body["field_errors"] == {"monthly_income": MSG_INCOME_PRIMARY}
    assert body["draft"]["data"]["income"]["liquid_assets"] == "180000"


async def test_resume_returns_first_incomplete_tab(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
) -> None:
    """AC3: tabs 1-2 done, tab 3 half-filled; a reload restores the values
    and resumes at tab 3."""
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    tabs = valid_tabs()
    for tab in ("you", "property"):
        response = await client.patch(
            f"{BASE}/{draft_id}/draft", json={"tab": tab, "data": tabs[tab]}
        )
        assert response.json()["tab_valid"] is True, response.json()
    half = {"monthly_debts": "300"}
    await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": "income", "data": half})

    reloaded = (await client.post(BASE)).json()
    assert reloaded["id"] == draft_id
    assert reloaded["current_tab"] == "income"
    assert reloaded["tabs"]["you"]["complete"] is True
    assert reloaded["tabs"]["property"]["complete"] is True
    assert reloaded["tabs"]["income"]["complete"] is False
    assert reloaded["data"]["you"]["first_name"] == "Tina"
    assert reloaded["data"]["income"]["monthly_debts"] == "300"

    # Finishing every tab resumes at the consent (submit) step.
    for tab in ("income", "consent"):
        await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": tab, "data": tabs[tab]})
    final = (await client.get(f"{BASE}/{draft_id}")).json()
    assert final["current_tab"] == "consent"
    assert all(status["complete"] for status in final["tabs"].values())


async def test_patch_rejects_unknown_tab(
    client: AsyncClient, make_borrower_session: Callable[..., Awaitable[Any]]
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    response = await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": "reo", "data": {}})
    assert response.status_code == 422


async def test_metros_for_the_picker(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
) -> None:
    """Review round 1, major 3: the borrower-side metro list for tab 2."""
    assert (await client.get(f"{BASE}/metros")).status_code == 401
    db_session.add_all(
        [
            ProviderListing(**_listing_fields(tampa_listing) | {"metro": "Davenport"}),
            ProviderListing(**_listing_fields(tampa_listing) | {"state": "AZ", "metro": "Phoenix"}),
        ]
    )
    await db_session.commit()
    await make_borrower_session()
    response = await client.get(f"{BASE}/metros")
    assert response.status_code == 200
    assert response.json() == {
        "states": [
            {"state": "AZ", "metros": ["Phoenix"]},
            {"state": "FL", "metros": ["Davenport", "Tampa"]},
        ]
    }


def _listing_fields(listing: ProviderListing) -> dict[str, Any]:
    return {
        column: getattr(listing, column)
        for column in (
            "address",
            "city",
            "state",
            "zip",
            "county",
            "metro",
            "list_price",
            "beds",
            "baths",
            "sqft",
            "property_type",
            "image_url",
            "deal_grade",
            "str_permitted",
        )
    }


async def test_422_bodies_never_echo_input(
    client: AsyncClient, make_borrower_session: Callable[..., Awaitable[Any]]
) -> None:
    """Review round 1 nit: a malformed body (an SSN pasted where the tab or
    data object belongs) is rejected without echoing the value back."""
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    for body in (
        {"tab": "123-45-6789", "data": {}},
        {"tab": "you", "data": "123-45-6789"},
    ):
        response = await client.patch(f"{BASE}/{draft_id}/draft", json=body)
        assert response.status_code == 422
        assert "123-45-6789" not in response.text
        assert all("input" not in error for error in response.json()["detail"])
