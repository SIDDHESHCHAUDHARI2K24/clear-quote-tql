"""`GET /api/v1/portal/me` (CQ-031 spec.md AC1-AC5)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.borrower.consent.models import Consent
from app.features.clients.models import Client
from app.features.quotes.send.models import QuotePackageVersion
from conftest import BorrowerSession

MakeBorrowerSession = Callable[..., Awaitable[BorrowerSession]]
MakeApplication = Callable[..., Awaitable[Application]]
MakeSentVersion = Callable[..., Awaitable[QuotePackageVersion]]
MakePendingConsent = Callable[..., Awaitable[Consent]]

_LO_FULL_NAME = "Taylor Morgan"
_LO_FIRST_NAME = "Taylor"


async def _make_lo(db_session: AsyncSession) -> User:
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
        password_hash="not-a-real-hash",
        role=UserRole.LO,
        full_name=_LO_FULL_NAME,
        phone="8135551234",
    )
    db_session.add(lo)
    await db_session.flush()
    return lo


# (persona label, seeded status) pairs mirror spec.md's persona table
# (docs/backlog/CQ-031-borrower-home/spec.md and the seed persona yaml
# files' `seed_end_status`), used here as fixture data via factories --
# not the real `seed.loader` pipeline, which is slow/integration-scale;
# the noapp/Marcus/Aisha/Luis personas are re-checked against the real
# seed at stage 7 (post-dev.md) per the coordinator's E2E note.
_IN_REVIEW_LABEL = "Your loan officer is reviewing your numbers"
_APPLIED_LABEL = "Application received"
_PREAPPROVED_LABEL = "Your pre-approval is ready"

PERSONA_STATUSES = [
    ("Marcus Hale", ApplicationStatus.PRICED, "in_review", _IN_REVIEW_LABEL),
    ("Kathleen Mcreynolds", ApplicationStatus.PRICED, "in_review", _IN_REVIEW_LABEL),
    ("Priya Nair", ApplicationStatus.PRICED, "in_review", _IN_REVIEW_LABEL),
    ("Daniel Ortiz", ApplicationStatus.PRICED, "in_review", _IN_REVIEW_LABEL),
    ("Sam Reed", ApplicationStatus.PRICED, "in_review", _IN_REVIEW_LABEL),
    ("Tom Brandt", ApplicationStatus.PRICED, "in_review", _IN_REVIEW_LABEL),
    ("Aisha Coleman", ApplicationStatus.NEEDS_ATTENTION, "applied", _APPLIED_LABEL),
    ("Ben Ford", ApplicationStatus.NEEDS_ATTENTION, "applied", _APPLIED_LABEL),
    ("Grace Kim", ApplicationStatus.SENT, "preapproved", _PREAPPROVED_LABEL),
    (
        "Luis Romero",
        ApplicationStatus.OPTION_SELECTED,
        "option_selected",
        f"You chose an option — {_LO_FIRST_NAME} will be in touch",
    ),
]


@pytest.mark.parametrize("persona,status,expected_stage,expected_label", PERSONA_STATUSES)
async def test_portal_stage_mapping(
    persona: str,
    status: ApplicationStatus,
    expected_stage: str,
    expected_label: str,
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: MakeApplication,
    make_borrower_session: MakeBorrowerSession,
) -> None:
    """AC1: each of the 10 personas' seeded status maps to the spec.md
    stage/label."""
    first_name, last_name = persona.split(" ", 1)
    lo = await _make_lo(db_session)
    application = await make_application(first_name=first_name, last_name=last_name, lo=lo)
    application.status = status
    await db_session.commit()

    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)

    response = await client.get("/api/v1/portal/me")

    assert response.status_code == 200
    body = response.json()
    assert len(body["applications"]) == 1
    item = body["applications"][0]
    assert item["stage"] == expected_stage
    assert item["label"] == expected_label


async def test_portal_hides_internal_states(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: MakeApplication,
    make_borrower_session: MakeBorrowerSession,
) -> None:
    """AC2: Aisha Coleman (needs_attention) sees "Application received",
    and no response for any status contains "attention"/"flag"/"error"."""
    lo = await _make_lo(db_session)
    banned = ("attention", "flag", "error")

    for status in ApplicationStatus:
        application = await make_application(
            first_name="Aisha" if status is ApplicationStatus.NEEDS_ATTENTION else "Test",
            last_name="Coleman" if status is ApplicationStatus.NEEDS_ATTENTION else "Persona",
            lo=lo,
        )
        application.status = status
        await db_session.commit()

        client_row = await db_session.get(Client, application.client_id)
        await make_borrower_session(client_row)

        response = await client.get("/api/v1/portal/me")
        assert response.status_code == 200
        raw = json.dumps(response.json()).lower()
        for word in banned:
            assert word not in raw, f"status={status}: response contains {word!r}: {raw}"

        if status is ApplicationStatus.NEEDS_ATTENTION:
            item = response.json()["applications"][0]
            assert item["label"] == "Application received"
            assert item["stage"] == "applied"


async def test_next_action_view_report_and_option_selected(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: MakeApplication,
    make_borrower_session: MakeBorrowerSession,
    make_sent_version: MakeSentVersion,
) -> None:
    """AC3: Marcus Hale's next action opens his latest sent version; Luis
    Romero (option_selected) gets `next_action.type = none` plus a
    `secondary_report_token` for "View your numbers"."""
    lo = await _make_lo(db_session)

    marcus = await make_application(first_name="Marcus", last_name="Hale", lo=lo)
    marcus.status = ApplicationStatus.SENT
    await db_session.commit()
    marcus_version = await make_sent_version(marcus)

    client_row = await db_session.get(Client, marcus.client_id)
    await make_borrower_session(client_row)
    response = await client.get("/api/v1/portal/me")
    assert response.status_code == 200
    item = response.json()["applications"][0]
    assert item["next_action"]["type"] == "view_report"
    assert item["next_action"]["report_token"] == marcus_version.report_token
    assert item["secondary_report_token"] is None

    luis = await make_application(first_name="Luis", last_name="Romero", lo=lo)
    luis.status = ApplicationStatus.OPTION_SELECTED
    await db_session.commit()
    luis_version = await make_sent_version(luis)

    luis_client_row = await db_session.get(Client, luis.client_id)
    await make_borrower_session(luis_client_row)
    response = await client.get("/api/v1/portal/me")
    assert response.status_code == 200
    item = response.json()["applications"][0]
    assert item["stage"] == "option_selected"
    assert item["next_action"]["type"] == "none"
    assert item["secondary_report_token"] == luis_version.report_token


async def test_authorize_credit_check_next_action(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: MakeApplication,
    make_borrower_session: MakeBorrowerSession,
    make_pending_consent: MakePendingConsent,
) -> None:
    lo = await _make_lo(db_session)
    application = await make_application(first_name="Sam", last_name="Reed", lo=lo)
    application.status = ApplicationStatus.PRICED
    await db_session.commit()
    consent = await make_pending_consent(application)

    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)

    response = await client.get("/api/v1/portal/me")
    assert response.status_code == 200
    item = response.json()["applications"][0]
    assert item["next_action"]["type"] == "authorize_credit_check"
    assert item["next_action"]["consent_id"] == str(consent.id)


async def test_pending_consent_skips_an_expired_newer_row(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: MakeApplication,
    make_borrower_session: MakeBorrowerSession,
    make_pending_consent: MakePendingConsent,
) -> None:
    """Review round 1 finding: an older, still-valid pending consent must
    not be skipped just because a newer pending row for the same
    application has since expired."""
    lo = await _make_lo(db_session)
    application = await make_application(first_name="Sam", last_name="Reed", lo=lo)
    application.status = ApplicationStatus.PRICED
    await db_session.commit()

    older_valid = await make_pending_consent(application, requested_days_ago=20, expires_in_days=30)
    await make_pending_consent(application, requested_days_ago=1, expires_in_days=-1)

    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)

    response = await client.get("/api/v1/portal/me")
    assert response.status_code == 200
    item = response.json()["applications"][0]
    assert item["next_action"]["type"] == "authorize_credit_check"
    assert item["next_action"]["consent_id"] == str(older_valid.id)


async def test_empty_state_no_applications(
    client: AsyncClient,
    make_borrower_session: MakeBorrowerSession,
) -> None:
    """AC4: a borrower with no applications sees an empty list."""
    await make_borrower_session(None)

    response = await client.get("/api/v1/portal/me")

    assert response.status_code == 200
    body = response.json()
    assert body["applications"] == []
    assert body["first_name"]
    assert body["email"]


async def test_portal_me_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: MakeApplication,
    make_borrower_session: MakeBorrowerSession,
) -> None:
    """AC5: a borrower can only see their own applications."""
    lo = await _make_lo(db_session)
    mine = await make_application(first_name="Owner", last_name="Borrower", lo=lo)
    other = await make_application(first_name="Other", last_name="Borrower", lo=lo)
    await db_session.commit()

    mine_client = await db_session.get(Client, mine.client_id)
    other_client = await db_session.get(Client, other.client_id)

    await make_borrower_session(mine_client)
    response = await client.get("/api/v1/portal/me")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["applications"]}
    assert ids == {str(mine.id)}
    assert str(other.id) not in ids

    await make_borrower_session(other_client)
    response = await client.get("/api/v1/portal/me")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["applications"]}
    assert ids == {str(other.id)}
    assert str(mine.id) not in ids


async def test_portal_me_requires_borrower_session(client: AsyncClient) -> None:
    response = await client.get("/api/v1/portal/me")
    assert response.status_code == 401
