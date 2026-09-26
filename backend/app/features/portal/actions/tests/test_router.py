"""`POST /api/v1/portal/reports/{token}/actions` (CQ-024 spec.md AC1-AC4)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.enums import ApplicationStatus, Occupancy
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.clients.models import Client
from app.features.notifications.outbox.models import OutboxEmail
from app.features.portal.reports.versions import freeze_package_version
from app.features.pricing.scenarios.service import auto_price
from app.features.quotes.builder.tests.test_review_round1 import (
    _application_lock,
    _capture_sql,
    _first,
)
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from app.integrations.crm.models import CrmEvent
from conftest import BorrowerSession

from .conftest import seed_conventional_rate_sheet

MakeBorrowerSession = Callable[..., Awaitable[BorrowerSession]]


def _options(version: QuotePackageVersion) -> list[dict[str, Any]]:
    assert isinstance(version.snapshot, dict)
    options = version.snapshot["options"]
    assert isinstance(options, list)
    return options


async def _sent_package(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    *,
    sent_days_ago: float = 0,
    first_name: str = "Marcus",
    last_name: str = "Hale",
) -> tuple[Application, QuotePackage, QuotePackageVersion]:
    application = await make_application(
        occupancy=Occupancy.PRIMARY,
        requested_price=Decimal("300000.00"),
        first_name=first_name,
        last_name=last_name,
    )
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0085"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    seed_conventional_rate_sheet(db_session)
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    quote_ids = list(pricing_result.quote_ids)
    package = QuotePackage(
        application_id=application.id,
        quote_ids=quote_ids,
        recommended_quote_id=quote_ids[0],
        report_token=f"pkg-{application.id}",
    )
    db_session.add(package)
    await db_session.flush()

    sent_at = datetime.now(UTC) - timedelta(days=sent_days_ago)
    application.status = ApplicationStatus.SENT
    await db_session.commit()

    version = await freeze_package_version(db_session, package=package, sent_at=sent_at)
    await db_session.commit()
    return application, package, version


async def _sign_in(
    db_session: AsyncSession, make_borrower_session: MakeBorrowerSession, application: Application
) -> None:
    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)


async def test_move_forward_sets_option_selected_sends_one_email_and_logs_activity_and_crm(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await _sign_in(db_session, make_borrower_session, application)

    buydown_quote_id = _options(version)[-1]["quote_id"]
    buydown_label = _options(version)[-1]["label"]

    response = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "move_forward", "quote_id": buydown_quote_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "option_selected"
    assert body["borrower_action"]["type"] == "move_forward"
    assert body["borrower_action"]["quote_id"] == buydown_quote_id

    await db_session.refresh(application)
    assert application.status is ApplicationStatus.OPTION_SELECTED

    emails = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(emails) == 1
    assert buydown_label in emails[0].subject
    assert "move forward" in emails[0].subject.lower()

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "quote.move_forward",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1

    crm_events = (await db_session.execute(select(CrmEvent))).scalars().all()
    assert len(crm_events) == 1
    assert crm_events[0].event_type == "borrower.move_forward"


async def test_move_forward_twice_second_is_409_no_new_email(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await _sign_in(db_session, make_borrower_session, application)
    quote_id = _options(version)[0]["quote_id"]

    first = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "move_forward", "quote_id": quote_id},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "move_forward", "quote_id": quote_id},
    )
    assert second.status_code == 409
    assert second.json()["error"]["details"]["status"] == "option_selected"

    third = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_other", "quote_id": quote_id, "message": "Can we revisit this?"},
    )
    assert third.status_code == 409

    emails = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(emails) == 1


async def test_ask_other_requires_message(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await _sign_in(db_session, make_borrower_session, application)
    quote_id = _options(version)[0]["quote_id"]

    empty = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_other", "quote_id": quote_id, "message": ""},
    )
    assert empty.status_code == 422

    missing = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_other", "quote_id": quote_id},
    )
    assert missing.status_code == 422

    too_long = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_other", "quote_id": quote_id, "message": "x" * 501},
    )
    assert too_long.status_code == 422


async def test_ask_other_sets_inquiry_and_emails_message(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await _sign_in(db_session, make_borrower_session, application)
    quote_id = _options(version)[0]["quote_id"]

    response = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={
            "type": "ask_other",
            "quote_id": quote_id,
            "message": "Could we lower the cash to close?",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "inquiry"

    await db_session.refresh(application)
    assert application.status is ApplicationStatus.INQUIRY

    emails = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(emails) == 1
    assert "Could we lower the cash to close?" in emails[0].html

    # AC3's rules table: ask_other remains allowed from Inquiry too.
    second = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_other", "quote_id": quote_id, "message": "One more thing"},
    )
    assert second.status_code == 200


async def test_expired_allows_only_ask_updated(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, _package, version = await _sent_package(
        db_session,
        make_application,
        set_field_value,
        sent_days_ago=25,
        first_name="Grace",
        last_name="Kim",
    )
    await _sign_in(db_session, make_borrower_session, application)
    quote_id = _options(version)[0]["quote_id"]

    move_forward = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "move_forward", "quote_id": quote_id},
    )
    assert move_forward.status_code == 409

    ask_other = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_other", "quote_id": quote_id, "message": "Please update"},
    )
    assert ask_other.status_code == 409

    ask_updated = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_updated"},
    )
    assert ask_updated.status_code == 200
    assert ask_updated.json()["status"] == "inquiry"

    await db_session.refresh(application)
    assert application.status is ApplicationStatus.INQUIRY

    emails = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(emails) == 1
    assert "asked for updated numbers" in emails[0].subject


@pytest.mark.parametrize(
    "terminal_status",
    [ApplicationStatus.OPTION_SELECTED, ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED],
)
async def test_ask_updated_refuses_to_resurrect_a_terminal_status(
    terminal_status: ApplicationStatus,
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """Review finding (PR #8 round 1, MAJOR): `ask_updated` only checked
    `expired`, so an expired version whose application had already reached
    a terminal status (a move_forward elsewhere, or an LO withdrawing/
    closing the file) could still be resurrected back to `inquiry`."""
    application, _package, version = await _sent_package(
        db_session,
        make_application,
        set_field_value,
        sent_days_ago=25,
        first_name="Terminal",
        last_name="Case",
    )
    application.status = terminal_status
    await db_session.commit()
    await _sign_in(db_session, make_borrower_session, application)

    response = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "ask_updated"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == terminal_status.value

    await db_session.refresh(application)
    assert application.status is terminal_status

    emails = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert emails == []

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(ActivityEvent.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert events == []


async def test_quote_id_must_be_one_of_the_snapshot_options(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await _sign_in(db_session, make_borrower_session, application)

    response = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "move_forward", "quote_id": "not-a-real-quote-id"},
    )
    assert response.status_code == 422


async def test_superseded_version_returns_409_for_every_action_type(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, package, old_version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await freeze_package_version(db_session, package=package)
    await db_session.commit()
    await _sign_in(db_session, make_borrower_session, application)
    quote_id = _options(old_version)[0]["quote_id"]

    move_forward = await client.post(
        f"/api/v1/portal/reports/{old_version.report_token}/actions",
        json={"type": "move_forward", "quote_id": quote_id},
    )
    assert move_forward.status_code == 409

    ask_updated = await client.post(
        f"/api/v1/portal/reports/{old_version.report_token}/actions",
        json={"type": "ask_updated"},
    )
    assert ask_updated.status_code == 409


async def test_report_not_found_message_matches_for_missing_and_foreign_token(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    quote_id = _options(version)[0]["quote_id"]

    await make_borrower_session(None)
    foreign = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "move_forward", "quote_id": quote_id},
    )
    assert foreign.status_code == 404

    missing = await client.post(
        "/api/v1/portal/reports/not-a-real-token/actions",
        json={"type": "move_forward", "quote_id": quote_id},
    )
    assert missing.status_code == 404

    assert foreign.json()["error"]["message"] == missing.json()["error"]["message"]


async def test_action_locks_package_then_version_then_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """U3 (PR #35 review minor d): the one lock order
    (applications/locking.py) on the portal side is package -> version ->
    application, asserted on the SQL the action actually runs."""
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await _sign_in(db_session, make_borrower_session, application)
    quote_id = _options(version)[0]["quote_id"]

    with _capture_sql() as statements:
        response = await client.post(
            f"/api/v1/portal/reports/{version.report_token}/actions",
            json={"type": "move_forward", "quote_id": quote_id},
        )
    assert response.status_code == 200, response.text

    package_lock = _first(statements, lambda s: "FROM quote_packages " in s and "FOR UPDATE" in s)
    version_lock = _first(
        statements, lambda s: "FROM quote_package_versions" in s and "FOR UPDATE" in s
    )
    app_lock = _application_lock(statements)
    assert package_lock is not None and version_lock is not None and app_lock is not None
    assert package_lock < version_lock < app_lock, statements


async def test_expiry_reads_the_injected_clock(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U3 (merge plan M5): a report sent today counts as expired when
    `CLOCK_NOW` is 22 days on, the same instant CQ-030's job and the report
    view use."""
    application, _package, version = await _sent_package(
        db_session, make_application, set_field_value
    )
    await _sign_in(db_session, make_borrower_session, application)
    frozen = get_settings().model_copy(
        update={"clock_now": (version.sent_at + timedelta(days=22)).isoformat()}
    )
    monkeypatch.setattr(clock, "get_settings", lambda: frozen)

    response = await client.post(
        f"/api/v1/portal/reports/{version.report_token}/actions",
        json={"type": "move_forward", "quote_id": _options(version)[0]["quote_id"]},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["message"] == "This report has expired."
