"""spec.md AC2/AC3: the outbox list, detail, attachment stream, and
scoping (plan.md decision 2: 404 for cross-scope, not the spec's literal
403; application-less emails are Manager/Admin only)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.notifications.outbox.models import OutboxEmail
from conftest import StaffSession


async def test_outbox_401_without_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/v1/outbox")
    assert response.status_code == 401


async def test_outbox_list_and_detail(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await make_outbox_email(
        application=application,
        subject="Your Clear Quote pre-approval is ready",
        html="<p>Your report is ready.</p>",
        attachment_keys=["outbox/fixture/quote.pdf"],
    )
    await db_session.commit()

    list_response = await client.get("/api/v1/outbox")
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["type"] == "quote_sent"
    assert row["client_name"] == "Test Client"
    assert row["status"] == "sent"
    assert row["sent_at"] is not None

    detail_response = await client.get(f"/api/v1/outbox/{row['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["html"] == "<p>Your report is ready.</p>"
    assert detail["attachments"] == [{"key": "outbox/fixture/quote.pdf", "filename": "quote.pdf"}]


async def test_outbox_filters(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await make_outbox_email(
        application=application, subject="Your Clear Quote sign-in code", to_email="a@x.test"
    )
    await make_outbox_email(
        application=application,
        subject="Your Clear Quote pre-approval is ready",
        to_email="b@x.test",
    )
    await db_session.commit()

    by_type = (await client.get("/api/v1/outbox", params={"type": "otp"})).json()
    assert by_type["total"] == 1
    assert by_type["items"][0]["to_email"] == "a@x.test"

    by_q = (await client.get("/api/v1/outbox", params={"q": "pre-approval"})).json()
    assert by_q["total"] == 1
    assert by_q["items"][0]["to_email"] == "b@x.test"

    by_app = (
        await client.get("/api/v1/outbox", params={"application_id": str(application.id)})
    ).json()
    assert by_app["total"] == 2


async def test_outbox_search_escapes_like_wildcards(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """Code review finding: `q` used to build an unescaped ILIKE pattern, so
    a literal `%`/`_` in the search text matched everything instead of
    matching literally."""
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await make_outbox_email(application=application, subject="100% approved", to_email="a@x.test")
    await make_outbox_email(
        application=application, subject="Your Clear Quote sign-in code", to_email="b@x.test"
    )
    await db_session.commit()

    # A literal "%" must not act as a wildcard matching every row.
    by_percent = (await client.get("/api/v1/outbox", params={"q": "100%"})).json()
    assert by_percent["total"] == 1
    assert by_percent["items"][0]["to_email"] == "a@x.test"

    # A bare "%" must match literally (only the row that actually contains
    # a "%" character), not act as a wildcard matching every row.
    by_bare_percent = (await client.get("/api/v1/outbox", params={"q": "%"})).json()
    assert by_bare_percent["total"] == 1
    assert by_bare_percent["items"][0]["to_email"] == "a@x.test"


async def test_outbox_access(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC3: an LO cannot open another LO's application's outbox email --
    404 (plan.md E16), never 403."""
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    email = await make_outbox_email(application=application)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO
    list_response = await client.get("/api/v1/outbox")
    assert list_response.json()["total"] == 0

    detail_response = await client.get(f"/api/v1/outbox/{email.id}")
    assert detail_response.status_code == 404
    assert detail_response.json()["error"]["code"] == "NOT_FOUND"

    attachment_response = await client.get(f"/api/v1/outbox/{email.id}/attachments/some-key")
    assert attachment_response.status_code == 404


async def test_outbox_no_application_email_is_manager_admin_only(
    client: AsyncClient,
    db_session: AsyncSession,
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    email = await make_outbox_email(application=None, subject="Contact us")
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)
    lo_list = (await client.get("/api/v1/outbox")).json()
    assert lo_list["total"] == 0
    lo_detail = await client.get(f"/api/v1/outbox/{email.id}")
    assert lo_detail.status_code == 404

    await make_staff_session(role=UserRole.MANAGER)
    manager_list = (await client.get("/api/v1/outbox")).json()
    assert manager_list["total"] == 1
    manager_detail = await client.get(f"/api/v1/outbox/{email.id}")
    assert manager_detail.status_code == 200


def _live_client_or_skip() -> Any:
    live_client = storage.get_client()
    try:
        live_client.list_buckets()
    except (EndpointConnectionError, ClientError, OSError) as exc:
        pytest.skip(f"local MinIO unreachable: {exc}")
    return live_client


async def test_outbox_attachment_stream(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC2 (E2E_NOTE / plan.md E13): the download route streams a real
    `core/storage` object -- checked here with a fixture attachment until
    CQ-020 writes real PDFs (`pending -- re-check after CQ-020`)."""
    live_client = _live_client_or_skip()
    bucket = storage.get_settings().s3_bucket
    key = f"outbox/tests/{uuid.uuid4()}.pdf"
    await storage.ensure_bucket(bucket, client=live_client)
    await storage.put_object(key, b"%PDF-1.4 fixture", "application/pdf", client=live_client)

    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    email = await make_outbox_email(application=application, attachment_keys=[key])
    await db_session.commit()

    response = await client.get(f"/api/v1/outbox/{email.id}/attachments/{key}")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 fixture"
    assert response.headers["content-type"] == "application/pdf"

    await storage.delete_object(key, client=live_client)


async def test_outbox_attachment_stream_404s_cleanly_for_a_missing_object(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """Code review finding (`astream_object` is a lazy async generator, and
    `StreamingResponse` sends headers before pulling the first chunk): a
    key that's registered on the email but missing from the object store
    must still come back as a clean 404, not a 200 that aborts mid-stream."""
    _live_client_or_skip()  # skip if MinIO is unreachable, for parity with the live route
    key = f"outbox/tests/missing-{uuid.uuid4()}.pdf"  # never uploaded

    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    email = await make_outbox_email(application=application, attachment_keys=[key])
    await db_session.commit()

    response = await client.get(f"/api/v1/outbox/{email.id}/attachments/{key}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_outbox_attachment_key_not_on_this_email_404s(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """Minor 4 (review round 1): the owning LO asks for a key that is a
    real object in storage but isn't in *this* email's `attachment_keys`
    -- `get_attachment_key` must still 404 it (never stream an arbitrary
    object key just because the caller can see the email)."""
    live_client = _live_client_or_skip()
    bucket = storage.get_settings().s3_bucket
    real_key = f"outbox/tests/{uuid.uuid4()}.pdf"
    await storage.ensure_bucket(bucket, client=live_client)
    await storage.put_object(real_key, b"%PDF-1.4 fixture", "application/pdf", client=live_client)

    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    email = await make_outbox_email(
        application=application, attachment_keys=["outbox/tests/registered.pdf"]
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/outbox/{email.id}/attachments/{real_key}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

    await storage.delete_object(real_key, client=live_client)


async def test_outbox_attachment_content_disposition(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """Nit (review round 1): `Content-Disposition` carries both a plain
    ASCII `filename` (older clients) and an RFC 5987 `filename*` (so a
    non-ASCII filename survives)."""
    live_client = _live_client_or_skip()
    bucket = storage.get_settings().s3_bucket
    key = f"outbox/tests/{uuid.uuid4()}-quote.pdf"
    await storage.ensure_bucket(bucket, client=live_client)
    await storage.put_object(key, b"%PDF-1.4 fixture", "application/pdf", client=live_client)

    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    email = await make_outbox_email(application=application, attachment_keys=[key])
    await db_session.commit()

    response = await client.get(f"/api/v1/outbox/{email.id}/attachments/{key}")
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    filename = key.rsplit("/", 1)[-1]
    assert f'filename="{filename}"' in disposition
    assert f"filename*=UTF-8''{filename}" in disposition

    await storage.delete_object(key, client=live_client)


async def test_outbox_unknown_type_is_422(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """Minor 5 (review round 1): `type` is a `Literal` of the known email
    types, so a typo'd/unknown `?type=` is a 422, not a silent empty
    result."""
    await make_staff_session(role=UserRole.LO)
    response = await client.get("/api/v1/outbox", params={"type": "not-a-real-type"})
    assert response.status_code == 422


async def test_outbox_application_id_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_outbox_email: Callable[..., Awaitable[OutboxEmail]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """Minor 8: `GET /outbox?application_id=` (the Outbox page's URL param,
    apps/lo-console/src/app/(staff)/outbox/page.tsx) scopes the list to
    just that application."""
    owner = await make_staff_session(role=UserRole.LO)
    application_a = await make_application(lo=owner.user)
    application_b = await make_application(lo=owner.user)
    await make_outbox_email(application=application_a, to_email="a@x.test")
    await make_outbox_email(application=application_b, to_email="b@x.test")
    await db_session.commit()

    response = await client.get("/api/v1/outbox", params={"application_id": str(application_a.id)})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["to_email"] == "a@x.test"
