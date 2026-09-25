"""Submit (CQ-032 AC4, AC5, AC6; plan.md decisions 9-18, 21-22)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationSource, ApplicationStatus, Occupancy, Strategy, UserRole
from app.features.applications.assets.models import Asset, Employment
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import User
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.clients.models import Client
from app.features.notifications.outbox.models import OutboxEmail
from app.features.portal.apply.consent_text import CONSENT_TEXT_VERSION, consent_text_hash
from app.features.portal.apply.models import ApplicationDraft
from app.integrations.property_search.models import ProviderListing
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE

from .conftest import FakeTemporal, SentEmail

Tabs = Callable[[], dict[str, dict[str, Any]]]
BASE = "/api/v1/portal/applications"


async def _complete_draft(client: AsyncClient, tabs: dict[str, dict[str, Any]]) -> str:
    draft_id: str = (await client.post(BASE)).json()["id"]
    for tab in ("you", "property", "income", "consent"):
        response = await client.patch(
            f"{BASE}/{draft_id}/draft", json={"tab": tab, "data": tabs[tab]}
        )
        assert response.json()["tab_valid"] is True, response.json()
    return draft_id


async def _application(db: AsyncSession, application_id: str) -> Application:
    application = await db.get(Application, uuid.UUID(application_id))
    assert application is not None
    return application


async def _make_lo(db: AsyncSession, name: str, active_apps: int, client_id: uuid.UUID) -> User:
    lo = User(
        email=f"{uuid.uuid4()}@clearquote-demo.test",
        password_hash="x",
        role=UserRole.LO,
        full_name=name,
    )
    db.add(lo)
    await db.flush()
    for _ in range(active_apps):
        db.add(Application(client_id=client_id, lo_id=lo.id, status=ApplicationStatus.PRICED))
    await db.flush()
    return lo


async def test_submit_writes_the_application_graph(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    session = await make_borrower_session()
    draft_id = await _complete_draft(client, valid_tabs())

    response = await client.post(f"{BASE}/{draft_id}/submit")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "intake"
    assert body["pipeline_started"] is True
    app_id = body["application_id"]

    application = await _application(db_session, app_id)
    assert application.source is ApplicationSource.PORTAL
    assert application.status is ApplicationStatus.INTAKE
    assert application.occupancy is Occupancy.INVESTMENT
    assert application.strategy is Strategy.STR
    assert application.requested_price == Decimal("400000.00")
    assert application.client_id == session.client.id
    assert application.los_loan_guid is None
    assert application.subject_state == "FL"

    prop = (
        await db_session.execute(select(Property).where(Property.application_id == application.id))
    ).scalar_one()
    assert prop.address_status is PropertyAddressStatus.TBD
    assert prop.buy_box_states == ["FL"]
    assert prop.buy_box_metros == ["Tampa"]
    assert prop.recommend_matches is True
    assert (prop.city, prop.state, prop.zip, prop.county) == (
        "Tampa",
        "FL",
        "33602",
        "Hillsborough",
    )

    [party] = (
        (
            await db_session.execute(
                select(ApplicationParty).where(ApplicationParty.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert party.role is PartyRole.BORROWER
    assert (party.first_name, party.last_name) == ("Tina", "Tampa")
    assert party.email == session.account.email
    assert party.cell_phone == "8135550142"
    assert party.no_co_applicant_check is True

    housing = (
        (
            await db_session.execute(
                select(HousingHistory).where(HousingHistory.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(h.sequence, h.state, h.residence_years, h.residence_months) for h in housing] == [
        (0, "FL", 3, 2)
    ]

    assets = (
        (await db_session.execute(select(Asset).where(Asset.application_id == application.id)))
        .scalars()
        .all()
    )
    assert [a.verified_amount for a in assets] == [Decimal("180000.00")]
    liabilities = (
        (
            await db_session.execute(
                select(Liability).where(Liability.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert [li.monthly_payment for li in liabilities] == [Decimal("450.00")]
    employment = (
        (
            await db_session.execute(
                select(Employment).where(Employment.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert employment == []  # STR applicant gave no employer

    fields = {
        fv.field_key: fv
        for fv in (
            await db_session.execute(
                select(FieldValue).where(FieldValue.application_id == application.id)
            )
        )
        .scalars()
        .all()
    }
    fico = fields["representative_fico"]
    assert isinstance(fico.value, int) and 680 <= fico.value < 800
    assert fields["down_payment_pct"].value == "0.25"
    assert fields["down_payment_pct"].source_ref == "borrower_portal"

    draft = await db_session.get(ApplicationDraft, uuid.UUID(draft_id))
    assert draft is not None and draft.submitted_application_id == application.id

    assert fake_temporal.started[0]["id"] == f"application-{app_id}"
    assert fake_temporal.started[0]["task_queue"] == APPLICATION_PIPELINE_TASK_QUEUE
    assert fake_temporal.started[0]["args"][1] == app_id

    # A second submit is refused; a new POST starts a fresh draft.
    again = await client.post(f"{BASE}/{draft_id}/submit")
    assert again.status_code == 409
    assert again.json()["error"]["details"]["application_id"] == app_id
    assert (await client.post(BASE)).json()["id"] != draft_id


async def test_ssn_encrypted_at_rest(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    """AC4: the raw column is not the digits; the ORM decrypts it."""
    await make_borrower_session()
    tabs = valid_tabs()
    tabs["you"]["has_co_borrower"] = True
    tabs["you"]["co_borrower"] = {
        "first_name": "Cody",
        "last_name": "Tampa",
        "email": "cody@example.com",
        "cell_phone": "8135550100",
        "dob": "1987-02-02",
        "ssn": "987654321",
        "marital_status": "unmarried",
        "dependents_count": 1,
    }
    draft_id = await _complete_draft(client, tabs)
    app_id = (await client.post(f"{BASE}/{draft_id}/submit")).json()["application_id"]

    raw = (
        await db_session.execute(
            text(
                "SELECT role::text, ssn_encrypted FROM application_parties "
                "WHERE application_id = :id ORDER BY role"
            ),
            {"id": app_id},
        )
    ).all()
    assert [role for role, _ in raw] == ["borrower", "co_borrower"]
    for _, stored in raw:
        assert stored is not None
        raw_bytes = bytes(stored)
        assert b"123456789" not in raw_bytes and b"987654321" not in raw_bytes
        assert raw_bytes not in (b"123456789", b"987654321")

    parties = {
        p.role: p
        for p in (
            await db_session.execute(
                select(ApplicationParty).where(ApplicationParty.application_id == uuid.UUID(app_id))
            )
        )
        .scalars()
        .all()
    }
    assert parties[PartyRole.BORROWER].ssn_encrypted == "123456789"
    assert parties[PartyRole.CO_BORROWER].ssn_encrypted == "987654321"
    assert parties[PartyRole.BORROWER].no_co_applicant_check is False


async def test_submit_assigns_lo_and_emails(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    """AC5: the LO with the fewest active applications gets it (ties
    alphabetical), an activity event records it, and exactly one email
    goes to that LO."""
    session = await make_borrower_session()  # creates "Test LO" with 0 apps
    other_client = Client(
        full_name="Other", email="other@example.com", assigned_lo_id=session.client.assigned_lo_id
    )
    db_session.add(other_client)
    await db_session.flush()
    # Test LO: 2 active; Zed: 1 active; Amy: 1 active + 3 closed -> Amy wins
    # the 1-1 tie with Zed alphabetically.
    for _ in range(2):
        db_session.add(
            Application(
                client_id=other_client.id,
                lo_id=session.client.assigned_lo_id,
                status=ApplicationStatus.PRICED,
            )
        )
    await _make_lo(db_session, "Zed Zulu", 1, other_client.id)
    amy = await _make_lo(db_session, "Amy Adams", 1, other_client.id)
    for _ in range(3):
        db_session.add(
            Application(client_id=other_client.id, lo_id=amy.id, status=ApplicationStatus.CLOSED)
        )
    await db_session.commit()

    draft_id = await _complete_draft(client, valid_tabs())
    body = (await client.post(f"{BASE}/{draft_id}/submit")).json()
    assert body["assigned_lo_name"] == "Amy Adams"

    application = await _application(db_session, body["application_id"])
    assert application.lo_id == amy.id
    await db_session.refresh(session.client)
    assert session.client.assigned_lo_id == amy.id

    events = (
        (
            await db_session.execute(
                select(ActivityEvent)
                .where(ActivityEvent.application_id == application.id)
                .order_by(ActivityEvent.type)
            )
        )
        .scalars()
        .all()
    )
    assigned = next(e for e in events if e.type == "application.assigned")
    assert assigned.payload == {
        "lo_id": str(amy.id),
        "lo_name": "Amy Adams",
        "rule": "least_loaded",
    }
    assert any(e.type == "application.submitted" for e in events)

    assert [(m.to, m.subject) for m in sent_emails] == [
        (amy.email, "New application from Tina Tampa")
    ]
    outbox = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert [o.to_email for o in outbox] == [amy.email]


async def test_submit_records_consent(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    """AC6: one accepted consent row with the text hash, time, IP and UA."""
    await make_borrower_session()
    draft_id = await _complete_draft(client, valid_tabs())
    app_id = (
        await client.post(f"{BASE}/{draft_id}/submit", headers={"user-agent": "WizardTest/1.0"})
    ).json()["application_id"]

    [consent] = (
        (
            await db_session.execute(
                select(Consent).where(Consent.application_id == uuid.UUID(app_id))
            )
        )
        .scalars()
        .all()
    )
    assert consent.type is ConsentType.APPLICATION
    assert consent.status is ConsentStatus.ACCEPTED
    assert consent.text_hash == consent_text_hash()
    assert len(consent.text_hash or "") == 64
    assert consent.text_version == CONSENT_TEXT_VERSION
    assert consent.typed_name == "tina  TAMPA"
    assert consent.ip == "127.0.0.1"
    assert consent.user_agent == "WizardTest/1.0"
    assert consent.at is not None and consent.decided_at == consent.at


async def test_submit_with_address_and_primary(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    await make_borrower_session()
    tabs = valid_tabs()
    tabs["you"] |= {"residence_years": 1, "residence_months": 2}
    tabs["you"]["prior_address"] = {
        "street": "9 Old St",
        "city": "Orlando",
        "state": "FL",
        "zip": "32801",
        "residence_years": 2,
        "residence_months": 0,
    }
    tabs["property"] = {
        "occupancy": "primary",
        "has_property": True,
        "address": {"street": "4412 W Gray St", "city": "Tampa", "state": "FL", "zip": "33602"},
        "target_price": "350000",
        "down_payment_pct": "0.10",
    }
    tabs["income"] = {
        "employer_name": "Acme",
        "years_employed": "4.5",
        "monthly_income": "9000",
        "monthly_debts": "0",
        "liquid_assets": "90000",
    }
    draft_id = await _complete_draft(client, tabs)
    app_id = (await client.post(f"{BASE}/{draft_id}/submit")).json()["application_id"]

    application = await _application(db_session, app_id)
    assert application.occupancy is Occupancy.PRIMARY
    assert application.strategy is None
    prop = (
        await db_session.execute(select(Property).where(Property.application_id == application.id))
    ).scalar_one()
    assert prop.address_status is PropertyAddressStatus.SPECIFIC_ADDRESS
    assert (prop.street_address, prop.county, prop.recommend_matches) == (
        "4412 W Gray St",
        "Hillsborough",
        False,
    )
    housing = (
        (
            await db_session.execute(
                select(HousingHistory)
                .where(HousingHistory.application_id == application.id)
                .order_by(HousingHistory.sequence)
            )
        )
        .scalars()
        .all()
    )
    assert [(h.sequence, h.city) for h in housing] == [(0, "Lakeland"), (1, "Orlando")]
    [employment] = (
        (
            await db_session.execute(
                select(Employment).where(Employment.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert (employment.employer_name, employment.monthly_income) == ("Acme", Decimal("9000.00"))
    liabilities = (
        (
            await db_session.execute(
                select(Liability).where(Liability.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert liabilities == []  # $0 debts -> no row


async def test_submit_rejects_incomplete_draft(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    tabs = valid_tabs()
    await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": "you", "data": tabs["you"]})
    response = await client.post(f"{BASE}/{draft_id}/submit")
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["first_invalid_tab"] == "property"
    assert set(details["field_errors"]) == {"property", "income", "consent"}
    assert fake_temporal.started == []


async def test_submit_survives_temporal_outage(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    await make_borrower_session()
    fake_temporal.fail = True
    draft_id = await _complete_draft(client, valid_tabs())
    response = await client.post(f"{BASE}/{draft_id}/submit")
    assert response.status_code == 200
    assert response.json()["pipeline_started"] is False
    application = await _application(db_session, response.json()["application_id"])
    assert application.status is ApplicationStatus.INTAKE
