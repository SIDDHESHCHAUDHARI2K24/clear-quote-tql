"""Draft document uploads (CQ-032 AC7; plan.md decisions 19-20)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.assets.models import Document
from app.features.portal.apply.documents import MSG_BAD_TYPE, MSG_TOO_LARGE
from app.integrations.property_search.models import ProviderListing

from .conftest import PDF_BYTES, PNG_BYTES, FakeTemporal, SentEmail, StubS3

Tabs = Callable[[], dict[str, dict[str, Any]]]
BASE = "/api/v1/portal/applications"


async def _upload(
    client: AsyncClient, draft_id: str, name: str, data: bytes, doc_type: str = "pay_stub"
) -> Any:
    return await client.post(
        f"{BASE}/{draft_id}/documents",
        files={"file": (name, data, "application/octet-stream")},
        data={"doc_type": doc_type},
    )


async def test_document_upload_limits(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: Callable[..., Awaitable[Any]],
    stub_storage: StubS3,
    tampa_listing: ProviderListing,
    valid_tabs: Tabs,
    fake_temporal: FakeTemporal,
    sent_emails: list[SentEmail],
) -> None:
    """AC7: an 11 MB file and a .exe are rejected with a clear message; a
    valid PDF becomes a `documents` row (the LO's checklist) at submit."""
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]

    too_big = b"%PDF" + b"0" * (11 * 1024 * 1024)
    response = await _upload(client, draft_id, "paystub.pdf", too_big)
    assert response.status_code == 413
    assert response.json()["error"]["message"] == MSG_TOO_LARGE

    response = await _upload(client, draft_id, "setup.exe", b"MZ\x90\x00")
    assert response.status_code == 415
    assert response.json()["error"]["message"] == MSG_BAD_TYPE

    # Right extension, wrong content.
    response = await _upload(client, draft_id, "fake.pdf", b"MZ\x90\x00")
    assert response.status_code == 415

    response = await _upload(client, draft_id, "bad-type.pdf", PDF_BYTES, doc_type="tax_return")
    assert response.status_code == 422
    assert stub_storage.keys() == []

    response = await _upload(client, draft_id, "Pay Stub.PDF", PDF_BYTES)
    assert response.status_code == 201
    doc = response.json()
    assert doc["doc_type"] == "pay_stub"
    assert doc["filename"] == "Pay Stub.PDF"
    assert doc["content_type"] == "application/pdf"
    assert doc["size_bytes"] == len(PDF_BYTES)
    [draft_key] = stub_storage.keys()
    assert draft_key == f"drafts/{draft_id}/documents/{doc['id']}.pdf"

    # The draft lists it (no storage key exposed); PATCHing income keeps it.
    tabs = valid_tabs()
    tabs["income"]["documents"] = []  # server-managed: ignored
    for tab in ("you", "property", "income", "consent"):
        body = (
            await client.patch(f"{BASE}/{draft_id}/draft", json={"tab": tab, "data": tabs[tab]})
        ).json()
    documents = body["draft"]["data"]["income"]["documents"]
    assert [d["id"] for d in documents] == [doc["id"]]
    assert "object_key" not in documents[0]

    submitted = await client.post(f"{BASE}/{draft_id}/submit")
    assert submitted.status_code == 200, submitted.json()
    application_id = submitted.json()["application_id"]

    rows = (
        (
            await db_session.execute(
                select(Document).where(Document.application_id == uuid.UUID(application_id))
            )
        )
        .scalars()
        .all()
    )
    assert [(row.doc_type, row.object_key) for row in rows] == [
        ("pay_stub", f"applications/{application_id}/documents/{doc['id']}.pdf")
    ]
    assert rows[0].received_at is not None
    assert stub_storage.keys() == [f"applications/{application_id}/documents/{doc['id']}.pdf"]

    # After submit the draft is closed to uploads.
    response = await _upload(client, draft_id, "w2.png", PNG_BYTES, doc_type="w2")
    assert response.status_code == 409


async def test_delete_document(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    stub_storage: StubS3,
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    doc = (await _upload(client, draft_id, "w2.png", PNG_BYTES, doc_type="w2")).json()
    assert len(stub_storage.keys()) == 1

    response = await client.delete(f"{BASE}/{draft_id}/documents/{doc['id']}")
    assert response.status_code == 204
    assert stub_storage.keys() == []
    draft = (await client.get(f"{BASE}/{draft_id}")).json()
    assert draft["data"]["income"]["documents"] == []

    response = await client.delete(f"{BASE}/{draft_id}/documents/{doc['id']}")
    assert response.status_code == 404
