"""CQ-020 AC1–AC7: the Send endpoints and the `SendQuotePackage` workflow,
end to end through the real routes, workflow and activities (Temporal test
environment), real MinIO and real WeasyPrint. SMTP is captured
(`smtp_outbox`) except in AC1, which goes through the real Mailpit."""

from __future__ import annotations

import asyncio
import io
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity
from temporalio.client import Client, WorkflowFailureError

from app.core import storage
from app.core.config import get_settings
from app.core.enums import ApplicationStatus, UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import User
from app.features.auth.sessions.service import COOKIE_NAMES, create_session
from app.features.clients.models import Client as ClientRow
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _seed
from app.features.quotes.delivery import steps
from app.features.quotes.delivery.email_template import BUTTON_LABEL, SUBJECT
from app.features.quotes.delivery.steps import report_url
from app.features.quotes.pdf.service import build_letter_context
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from app.integrations.crm.models import CrmEvent
from app.workflows import send_activities
from app.workflows.constants import send_workflow_id
from app.workflows.send_quote_package import SendQuotePackageWorkflow
from conftest import BorrowerSession, StaffSession

from .conftest import SentMail

MakeStaff = Callable[..., Awaitable[StaffSession]]
MakeBorrower = Callable[..., Awaitable[BorrowerSession]]

MAILPIT_API_URL = os.environ.get("MAILPIT_API_URL", "http://localhost:8025")


async def _ready_package(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> tuple[uuid.UUID, dict[str, Any]]:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    response = await client.get(f"/api/v1/applications/{application_id}/package")
    assert response.status_code == 200, response.text
    package = response.json()
    readiness = (await client.get(f"/api/v1/packages/{package['id']}/readiness")).json()
    assert readiness == {"ready": True, "blockers": []}
    return application_id, package


async def _send(client: AsyncClient, temporal: Client, package_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/v1/packages/{package_id}/send")
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    assert body["status"] == "queued"
    await temporal.get_workflow_handle(body["workflow_id"]).result()
    return body


async def _versions(db: AsyncSession, package_id: str) -> list[QuotePackageVersion]:
    return list(
        (
            await db.execute(
                select(QuotePackageVersion)
                .where(QuotePackageVersion.package_id == uuid.UUID(package_id))
                .order_by(QuotePackageVersion.version)
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )


def _pdf_objects(package_id: str) -> list[str]:
    listing = storage.get_client().list_objects_v2(
        Bucket=get_settings().s3_bucket, Prefix=f"packages/{package_id}/"
    )
    return [item["Key"] for item in listing.get("Contents", [])]


# --- AC1 ---------------------------------------------------------------------


async def _mailpit_message(to: str, timeout: float = 10.0) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=MAILPIT_API_URL, timeout=5.0) as mailpit:
        for _ in range(int(timeout / 0.2)):
            search = await mailpit.get("/api/v1/search", params={"query": f'to:"{to}"'})
            search.raise_for_status()
            messages = search.json()["messages"]
            if messages:
                assert len(messages) == 1, messages
                detail = await mailpit.get(f"/api/v1/message/{messages[0]['ID']}")
                detail.raise_for_status()
                body: dict[str, Any] = detail.json()
                return body
            await asyncio.sleep(0.2)
    raise AssertionError(f"no Mailpit message to {to}")


async def test_send_email_arrives_with_pdf(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    temporal_client_override: Client,
    run_send_worker: Any,
) -> None:
    """AC1: one email in Mailpit to Marcus Hale's address, with the PDF
    attached and a "See your numbers" link to `/report/{token}` of a
    version that is his -- it opens once he signs in (CQ-022's route)."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    application = await db_session.get(Application, application_id)
    assert application is not None
    marcus = await db_session.get(ClientRow, application.client_id)
    assert marcus is not None
    # Mailpit is shared across worktrees: a unique address for this run.
    marcus.email = f"marcus.hale+{uuid.uuid4().hex[:10]}@clearquote-demo.test"
    await db_session.commit()

    async with run_send_worker():
        await _send(client, temporal_client_override, package["id"])

    message = await _mailpit_message(marcus.email)
    assert [a["Address"] for a in message["To"]] == [marcus.email]
    assert message["Subject"] == SUBJECT
    attachments = message["Attachments"]
    assert [(a["FileName"], a["ContentType"]) for a in attachments] == [
        ("preapproval-letter.pdf", "application/pdf")
    ]
    [version] = await _versions(db_session, package["id"])
    link = report_url(version.report_token)
    assert link.endswith(f"/report/{version.report_token}")
    assert f'href="{link}"' in message["HTML"]
    assert BUTTON_LABEL in message["HTML"]
    assert link in message["Text"]

    # The link's version belongs to him: signed in as Marcus, the portal
    # report opens (H2: the token only selects the version).
    await make_borrower_session(client_row=marcus)
    report = await client.get(f"/api/v1/portal/reports/{version.report_token}")
    assert report.status_code == 200, report.text
    assert report.json()["header"]["first_name"] == "Marcus"


# --- AC2 ---------------------------------------------------------------------


async def test_letter_pdf_contents(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """AC2: name, purchase price, LTV, term, FICO bracket, the LO's NMLS and
    the portal URL; one page, US Letter."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    async with run_send_worker():
        await _send(client, temporal_client_override, package["id"])

    response = await client.get(f"/api/v1/packages/{package['id']}/letter.pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert (round(float(page.mediabox.width)), round(float(page.mediabox.height))) == (612, 792)
    text = " ".join(page.extract_text().split())
    compact = re.sub(r"\s+", "", page.extract_text())

    [version] = await _versions(db_session, package["id"])
    row = await db_session.get(QuotePackage, uuid.UUID(package["id"]))
    assert row is not None
    ctx = await build_letter_context(db_session, row, portal_url=report_url(version.report_token))
    assert ctx.borrower_name == "Marcus Hale"
    assert ctx.lo_nmls and ctx.fico_bracket
    for expected in (
        ctx.borrower_name,
        ctx.purchase_price,
        ctx.ltv_percentage,
        f"{ctx.loan_term_years}",
        ctx.fico_bracket,
        ctx.lo_nmls,
    ):
        assert expected in text, expected
    assert f"{ctx.loan_term_years} YR" in text
    assert report_url(version.report_token) in compact
    # The email carried the same PDF.
    [mail] = smtp_outbox
    assert [a.filename for a in mail.attachments] == ["preapproval-letter.pdf"]
    assert mail.attachments[0].content == response.content


# --- AC3 ---------------------------------------------------------------------


async def test_send_records_status_events_outbox(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """AC3: status Sent, `sent_at`/`expires_at` (+21 days), one activity
    event, one CRM event and one outbox row referencing the PDF key."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    async with run_send_worker():
        started = await _send(client, temporal_client_override, package["id"])

    application = await db_session.get(Application, application_id, populate_existing=True)
    assert application is not None
    assert application.status is ApplicationStatus.SENT

    [version] = await _versions(db_session, package["id"])
    assert version.send_workflow_id == started["workflow_id"]
    assert version.expires_at - version.sent_at == timedelta(days=21)
    assert version.letter_key == f"packages/{package['id']}/v1/preapproval-letter.pdf"
    assert _pdf_objects(package["id"]) == [version.letter_key]

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application_id,
                    ActivityEvent.type == "quote.sent",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert isinstance(events[0].payload, dict)
    assert events[0].payload["package_id"] == package["id"]
    assert events[0].payload["version_id"] == str(version.id)

    client_row = await db_session.get(ClientRow, application.client_id)
    assert client_row is not None
    crm = (
        (
            await db_session.execute(
                select(CrmEvent).where(
                    CrmEvent.contact_id == (client_row.crm_contact_id or str(client_row.id)),
                    CrmEvent.event_type == "quote.sent",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(crm) == 1

    outbox = (
        (
            await db_session.execute(
                select(OutboxEmail).where(
                    OutboxEmail.application_id == application_id, OutboxEmail.subject == SUBJECT
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(outbox) == 1
    assert outbox[0].attachment_keys == [version.letter_key]
    assert outbox[0].status is EmailStatus.SENT
    assert outbox[0].id == version.outbox_email_id
    assert len(smtp_outbox) == 1 and smtp_outbox[0].to == client_row.email

    status = (await client.get(f"/api/v1/packages/{package['id']}/send-status")).json()
    assert status["status"] == "done"
    assert status["workflow_id"] == started["workflow_id"]
    assert status["version"] == 1
    assert status["recipient_email"] == client_row.email
    assert status["error"] is None

    [listed] = (await client.get(f"/api/v1/packages/{package['id']}/versions")).json()
    assert listed["version"] == 1
    assert listed["letter_url"] == f"/api/v1/packages/{package['id']}/letter.pdf?version=1"
    assert listed["outbox_email_id"] == str(outbox[0].id)
    assert listed["email_status"] == "sent"
    assert listed["report_url"] == report_url(version.report_token)
    assert listed["superseded"] is False

    refreshed = (await client.get(f"/api/v1/applications/{application_id}/package")).json()
    assert refreshed["sent_at"] is not None


# --- AC4 ---------------------------------------------------------------------


async def test_send_refuses_when_not_ready(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    send_queue: str,
    smtp_outbox: list[SentMail],
) -> None:
    """AC4: 409 with the blocker list; nothing frozen, started or sent."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    await db_session.execute(
        update(Quote)
        .where(Quote.id.in_([uuid.UUID(q) for q in package["quote_ids"]]))
        .values(stale=True)
    )
    await db_session.commit()

    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "PACKAGE_NOT_READY"
    assert error["details"]["blockers"][0] == {
        "code": "quotes_stale",
        "message": "Quotes are out of date",
        "tab": "pricing",
    }
    assert await _versions(db_session, package["id"]) == []
    row = await db_session.get(QuotePackage, uuid.UUID(package["id"]), populate_existing=True)
    assert row is not None and row.send_status is None and row.send_workflow_id is None
    assert smtp_outbox == []
    status = (await client.get(f"/api/v1/packages/{package['id']}/send-status")).json()
    assert status["status"] == "idle"


async def test_send_refuses_a_closed_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    send_queue: str,
) -> None:
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    application = await db_session.get(Application, application_id)
    assert application is not None
    application.status = ApplicationStatus.WITHDRAWN
    await db_session.commit()
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    assert response.status_code == 409
    codes = [b["code"] for b in response.json()["error"]["details"]["blockers"]]
    assert codes == ["application_closed"]


# --- AC5 ---------------------------------------------------------------------


def _crash_once_after(real: Callable[..., Awaitable[Any]], name: str) -> Callable[..., Any]:
    """The real activity, but attempt 1 "dies" right after its side effects
    committed -- the worst case for exactly-once."""

    @activity.defn(name=name)
    async def _wrapped(*args: Any) -> Any:
        result = await real(*args)
        if activity.info().attempt == 1:
            raise RuntimeError(f"worker died after {name}")
        return result

    return _wrapped


async def test_send_workflow_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """AC5: every activity crashes once after its side effects, and the
    worker running the workflow is shut down mid-send and replaced by a new
    one -- the send still completes exactly once: one version, one PDF,
    one email, one outbox row, one activity event, one CRM event."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    emailed = asyncio.Event()

    @activity.defn(name="email_borrower")
    async def _email_then_die(version_id: str, workflow_id: str) -> str:
        # Worker 1 delivers the email, then dies before reporting success.
        await send_activities.email_borrower(version_id, workflow_id)
        emailed.set()
        raise RuntimeError("worker 1 killed after emailing")

    first_worker_activities = [
        _crash_once_after(send_activities.freeze_package, "freeze_package"),
        _crash_once_after(send_activities.render_letter_pdf, "render_letter_pdf"),
        _email_then_die,
        send_activities.record_send,
        send_activities.mark_send_failed,
    ]
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    assert response.status_code == 202, response.text
    workflow_id = response.json()["workflow_id"]

    async with run_send_worker(first_worker_activities):
        await asyncio.wait_for(emailed.wait(), timeout=30)
    # Worker 1 is gone; a fresh worker (fresh workflow cache: it replays the
    # history) picks the retry up.
    second_worker_activities = [
        send_activities.freeze_package,
        send_activities.render_letter_pdf,
        _crash_once_after(send_activities.email_borrower, "email_borrower"),
        _crash_once_after(send_activities.record_send, "record_send"),
        send_activities.mark_send_failed,
    ]
    async with run_send_worker(second_worker_activities):
        await temporal_client_override.get_workflow_handle(workflow_id).result()

    versions = await _versions(db_session, package["id"])
    assert len(versions) == 1
    assert _pdf_objects(package["id"]) == [versions[0].letter_key]
    assert len(smtp_outbox) == 1
    outbox_count = (
        await db_session.execute(
            select(func.count())
            .select_from(OutboxEmail)
            .where(OutboxEmail.application_id == application_id, OutboxEmail.subject == SUBJECT)
        )
    ).scalar_one()
    assert outbox_count == 1
    event_count = (
        await db_session.execute(
            select(func.count())
            .select_from(ActivityEvent)
            .where(
                ActivityEvent.application_id == application_id,
                ActivityEvent.type == "quote.sent",
            )
        )
    ).scalar_one()
    assert event_count == 1
    crm_count = (
        await db_session.execute(
            select(func.count())
            .select_from(CrmEvent)
            .where(
                CrmEvent.event_type == "quote.sent",
                CrmEvent.payload["package_id"].astext == package["id"],
            )
        )
    ).scalar_one()
    assert crm_count == 1
    status_response = await client.get(f"/api/v1/packages/{package['id']}/send-status")
    assert status_response.status_code == 200, status_response.text
    status = status_response.json()
    assert status["status"] == "done"


async def test_double_click_returns_the_running_send(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """plan.md Decision 9: a second POST while a send is in flight starts
    nothing and answers with the running workflow id."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    first = await client.post(f"/api/v1/packages/{package['id']}/send")
    second = await client.post(f"/api/v1/packages/{package['id']}/send")
    assert first.status_code == second.status_code == 202
    assert second.json()["workflow_id"] == first.json()["workflow_id"]
    async with run_send_worker():
        await temporal_client_override.get_workflow_handle(first.json()["workflow_id"]).result()
    assert len(await _versions(db_session, package["id"])) == 1
    assert len(smtp_outbox) == 1


async def test_send_fails_cleanly_when_the_package_goes_stale(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """plan.md Decision 12: Freeze re-checks readiness; a package that went
    stale after `POST /send` fails with the reason and sends nothing."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    assert response.status_code == 202
    await db_session.execute(
        update(Quote)
        .where(Quote.id.in_([uuid.UUID(q) for q in package["quote_ids"]]))
        .values(stale=True)
    )
    await db_session.commit()
    async with run_send_worker():
        with pytest.raises(WorkflowFailureError):
            await temporal_client_override.get_workflow_handle(
                response.json()["workflow_id"]
            ).result()
    status = (await client.get(f"/api/v1/packages/{package['id']}/send-status")).json()
    assert status["status"] == "failed"
    assert status["error"] == "Quotes are out of date"
    assert await _versions(db_session, package["id"]) == []
    assert smtp_outbox == []


# --- AC6 ---------------------------------------------------------------------


async def test_resend_supersedes_previous(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """AC6: two sends, two versions (two PDFs); the first version's view
    model says `superseded=true` and points at the newest token."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    async with run_send_worker():
        await _send(client, temporal_client_override, package["id"])
        await _send(client, temporal_client_override, package["id"])

    first, second = await _versions(db_session, package["id"])
    assert (first.version, second.version) == (1, 2)
    assert first.superseded is True and second.superseded is False
    assert first.report_token != second.report_token
    assert sorted(_pdf_objects(package["id"])) == [first.letter_key, second.letter_key]
    assert len(smtp_outbox) == 2

    listed = (await client.get(f"/api/v1/packages/{package['id']}/versions")).json()
    assert [(v["version"], v["superseded"]) for v in listed] == [(2, False), (1, True)]
    v1_pdf = await client.get(f"/api/v1/packages/{package['id']}/letter.pdf?version=1")
    assert v1_pdf.status_code == 200 and v1_pdf.content.startswith(b"%PDF")

    application = await db_session.get(Application, application_id)
    assert application is not None
    marcus = await db_session.get(ClientRow, application.client_id)
    await make_borrower_session(client_row=marcus)
    old = (await client.get(f"/api/v1/portal/reports/{first.report_token}")).json()
    assert old["header"]["superseded"] is True
    assert old["newest_report_token"] == second.report_token


# --- AC7 ---------------------------------------------------------------------


async def test_letter_pdf_access(
    client: AsyncClient,
    db_session: AsyncSession,
    valkey: Redis,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """AC7, with plan.md Decision 1: an LO not assigned to the application
    gets **404** (Decision #11 / D6), not 403 -- a probe can't tell "not
    yours" from "doesn't exist". Signed out is 401; the assigned LO and a
    manager get the PDF."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    async with run_send_worker():
        await _send(client, temporal_client_override, package["id"])
    url = f"/api/v1/packages/{package['id']}/letter.pdf"

    assert (await client.get(url)).status_code == 200  # manager

    await make_staff_session(role=UserRole.LO)
    denied = await client.get(url)
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "NOT_FOUND"
    for path in ("send-status", "versions"):
        assert (await client.get(f"/api/v1/packages/{package['id']}/{path}")).status_code == 404
    assert (await client.post(f"/api/v1/packages/{package['id']}/send")).status_code == 404

    application = await db_session.get(Application, application_id)
    assert application is not None
    assigned = await db_session.get(User, application.lo_id)
    assert assigned is not None and assigned.role is UserRole.LO
    token = await create_session(valkey, principal="staff", subject_id=str(assigned.id))
    client.cookies.set(COOKIE_NAMES["staff"], token)
    allowed = await client.get(url)
    assert allowed.status_code == 200
    assert allowed.content.startswith(b"%PDF")

    client.cookies.clear()
    assert (await client.get(url)).status_code == 401


async def test_letter_pdf_404_before_any_send(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    _, package = await _ready_package(client, db_session, make_staff_session)
    response = await client.get(f"/api/v1/packages/{package['id']}/letter.pdf")
    assert response.status_code == 404
    assert (await client.get(f"/api/v1/packages/{package['id']}/versions")).json() == []


# --- M3 (plan.md Decision 2) -------------------------------------------------


async def test_put_on_sent_package_reopens_draft(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """A PUT on a sent package reopens it as the working draft; the sent
    version (snapshot, PDF, token) is untouched."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    async with run_send_worker():
        await _send(client, temporal_client_override, package["id"])
    [before] = await _versions(db_session, package["id"])
    snapshot = before.snapshot

    response = await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={
            "quote_ids": package["quote_ids"][:1],
            "recommended_quote_id": package["quote_ids"][0],
            "lo_note": "Revised",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == package["id"]
    assert body["sent_at"] is None
    assert body["quote_ids"] == package["quote_ids"][:1]

    [after] = await _versions(db_session, package["id"])
    assert after.snapshot == snapshot
    assert after.letter_key == before.letter_key


async def test_put_during_send_is_409(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    send_queue: str,
) -> None:
    """A PUT while the send's workflow is still running is refused (a dead
    send doesn't block it: `test_put_after_a_terminated_send_saves`)."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    workflow_id = send_workflow_id(package["id"], "running")
    handle = await temporal_client_override.start_workflow(
        SendQuotePackageWorkflow.run, package["id"], id=workflow_id, task_queue=send_queue
    )
    try:
        await db_session.execute(
            update(QuotePackage)
            .where(QuotePackage.id == uuid.UUID(package["id"]))
            .values(send_status="rendering", send_workflow_id=workflow_id)
        )
        await db_session.commit()
        response = await client.put(
            f"/api/v1/applications/{application_id}/package",
            json={
                "quote_ids": package["quote_ids"],
                "recommended_quote_id": package["quote_ids"][0],
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SEND_IN_PROGRESS"
    finally:
        await handle.terminate("test cleanup")


async def test_record_links_the_answered_inquiry(
    db_session: AsyncSession,
    client: AsyncClient,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """plan.md Decision 3: a send that answers an Inquiry records the link
    on the `quote.sent` event."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    application = await db_session.get(Application, application_id)
    assert application is not None
    application.status = ApplicationStatus.INQUIRY
    await db_session.commit()
    async with run_send_worker():
        await _send(client, temporal_client_override, package["id"])
    payload: Any = (
        await db_session.execute(
            select(ActivityEvent.payload).where(
                ActivityEvent.application_id == application_id,
                ActivityEvent.type == steps.SENT_EVENT_TYPE,
            )
        )
    ).scalar_one()
    assert isinstance(payload, dict)
    assert payload["in_reply_to_inquiry"] is True
    assert payload["previous_status"] == "inquiry"
