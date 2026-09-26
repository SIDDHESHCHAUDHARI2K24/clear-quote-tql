"""Credit actions: import liabilities (AC4) and hard-pull request (AC5, E11)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.enums import Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.sections import service as section_service
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.schemas import ScenarioSnapshot
from app.features.borrower.consent.models import Consent, ConsentStatus
from app.features.notifications.email import service as email_service
from app.features.notifications.outbox.models import OutboxEmail

MakeApp = Callable[..., Awaitable[Application]]


def _p(event: ActivityEvent) -> dict[str, Any]:
    assert isinstance(event.payload, dict)
    return event.payload


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    outbox: list[dict[str, str]] = []

    async def _fake_send(*, to: str, subject: str, html: str) -> None:
        outbox.append({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr(email_service, "smtp_send", _fake_send)
    return outbox


def _liabilities(section: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in section["records"] if r["kind"] == "liability"]


def _value(record: dict[str, Any], column: str) -> Any:
    return next(f["value"] for f in record["fields"] if f["field_key"].endswith(f".{column}"))


async def test_import_liabilities_keeps_manual(
    client: AsyncClient, make_app: MakeApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: imported rows are replaced from the LOS, a manual row is kept,
    and the primary DTI is recomputed."""

    async def _snapshot(*_args: object) -> ScenarioSnapshot:
        return ScenarioSnapshot(
            total_cash_to_close=Decimal("60000"), total_monthly_payment=Decimal("1500.00")
        )

    monkeypatch.setattr(section_service, "latest_scenario_snapshot", _snapshot)
    app = await make_app(
        occupancy=Occupancy.PRIMARY,
        monthly_income="10000.00",
        liabilities=[("Wells Fargo", "410.00"), ("Capital One", "90.00")],
    )
    base = f"/api/v1/applications/{app.id}"
    section = (await client.get(f"{base}/sections/credit")).json()
    wells = next(r for r in _liabilities(section) if _value(r, "creditor_name") == "Wells Fargo")

    # LO edits an imported row and adds a manual one.
    await client.patch(f"{base}/liabilities/{wells['id']}", json={"monthly_payment": "999.00"})
    manual = await client.post(
        f"{base}/liabilities",
        json={
            "creditor_name": "Student Loan",
            "account_type": "Installment",
            "monthly_payment": "250.00",
            "balance": "20000.00",
        },
    )
    before = manual.json()["credit"]
    # (999 + 90 + 250 + 1500) / 10000
    assert Decimal(before["dti"]) == Decimal("0.2839")

    response = await client.post(f"{base}/credit/import-liabilities")

    assert response.status_code == 200
    body = response.json()
    rows = _liabilities(body)
    by_name = {_value(r, "creditor_name"): r for r in rows}
    assert set(by_name) == {"Wells Fargo", "Capital One", "Student Loan"}
    assert _value(by_name["Wells Fargo"], "monthly_payment") == "410.00"
    assert by_name["Student Loan"]["manual"] is True
    assert by_name["Wells Fargo"]["manual"] is False
    assert not any(f["overridden"] for r in rows for f in r["fields"])
    # (410 + 90 + 250 + 1500) / 10000
    assert Decimal(body["credit"]["liabilities_monthly_total"]) == Decimal("750.00")
    assert Decimal(body["credit"]["dti"]) == Decimal("0.2250")


async def test_import_liabilities_event(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app()

    await client.post(f"/api/v1/applications/{app.id}/credit/import-liabilities")

    [event] = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == app.id,
                    ActivityEvent.type == "credit.liabilities_imported",
                )
            )
        )
        .scalars()
        .all()
    )
    assert _p(event)["imported"] == 1


async def test_hard_pull_request_once(
    client: AsyncClient,
    make_app: MakeApp,
    db_session: AsyncSession,
    sent: list[dict[str, str]],
) -> None:
    """AC5: one pending request, one email with the consent link, 409 on a
    second request while pending; the Credit section reports it (E11)."""
    app = await make_app(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)
    url = f"/api/v1/applications/{app.id}/credit/hard-pull-request"

    first = await client.post(url)

    assert first.status_code == 201
    consent = first.json()["consent"]
    assert consent["status"] == "pending"
    assert first.json()["section"]["credit"]["consent"]["id"] == consent["id"]
    row = await db_session.get(Consent, consent["id"])
    assert row is not None
    assert row.requested_at is not None and row.expires_at is not None
    assert row.expires_at - row.requested_at == timedelta(days=14)
    assert len(sent) == 1
    assert f"/tasks/credit-check/{consent['id']}" in sent[0]["html"]
    outbox = (
        (await db_session.execute(select(OutboxEmail).where(OutboxEmail.application_id == app.id)))
        .scalars()
        .all()
    )
    assert len(outbox) == 1
    event_payload: Any = (
        await db_session.execute(
            select(ActivityEvent.payload).where(
                ActivityEvent.application_id == app.id,
                ActivityEvent.type == "credit.hard_pull_requested",
            )
        )
    ).scalar_one()
    assert "@" not in str(event_payload)  # no borrower email in the timeline

    second = await client.post(url)

    assert second.status_code == 409
    assert len(sent) == 1
    count = (
        (await db_session.execute(select(Consent).where(Consent.application_id == app.id)))
        .scalars()
        .all()
    )
    assert len(count) == 1

    credit = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()["credit"]
    assert credit["consent"]["status"] == "pending"
    assert credit["consent"]["requested_at"] is not None


async def test_expired_request_allows_a_new_one(
    client: AsyncClient,
    make_app: MakeApp,
    db_session: AsyncSession,
    sent: list[dict[str, str]],
) -> None:
    app = await make_app()
    url = f"/api/v1/applications/{app.id}/credit/hard-pull-request"
    first = (await client.post(url)).json()["consent"]
    row = await db_session.get(Consent, first["id"])
    assert row is not None
    row.expires_at = now() - timedelta(minutes=1)
    await db_session.commit()

    credit = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()["credit"]
    assert credit["consent"]["status"] == "expired"

    assert (await client.post(url)).status_code == 201
    assert len(sent) == 2


async def test_consent_fico_after_hard_pull(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession, sent: list[dict[str, str]]
) -> None:
    """E11: after CQ-033 records an accepted consent and a hard-pull FICO
    (`source_ref="hard_pull"`), the section shows it."""
    from app.features.applications.verification.models import FieldValue

    app = await make_app(fico=700)
    consent_id = (
        await client.post(f"/api/v1/applications/{app.id}/credit/hard-pull-request")
    ).json()["consent"]["id"]
    row = await db_session.get(Consent, consent_id)
    assert row is not None
    row.status = ConsentStatus.ACCEPTED
    row.decided_at = now()
    fico = (
        await db_session.execute(
            select(FieldValue).where(
                FieldValue.application_id == app.id, FieldValue.field_key == "representative_fico"
            )
        )
    ).scalar_one()
    fico.value = 721
    fico.source_ref = "hard_pull"
    await db_session.commit()

    credit = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()["credit"]

    assert credit["pull_type"] == "hard_pull"
    assert credit["consent"]["status"] == "accepted"
    assert credit["consent"]["fico_after_pull"] == 721
    assert credit["fico_bracket"] == "720–739"
