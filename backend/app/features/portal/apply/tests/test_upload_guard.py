"""Upload bodies are bounded before parsing or auth (review round 1,
major 2 and minor 4; plan.md decision 26)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from starlette.requests import Request

from app.features.portal.apply import documents
from app.features.portal.apply.documents import MAX_DOCUMENTS_PER_DRAFT, MSG_TOO_LARGE

from .conftest import PDF_BYTES, PNG_BYTES, StubS3

BASE = "/api/v1/portal/applications"


@pytest.fixture
def form_calls(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts multipart parses (`Request.form`): a rejected body must never
    reach the parser (which spools file parts to disk)."""
    calls: list[int] = []
    original = Request.form

    def _spy(self: Request, **kwargs: Any) -> Any:
        calls.append(1)
        return original(self, **kwargs)

    monkeypatch.setattr(Request, "form", _spy)
    return calls


async def test_oversized_content_length_is_rejected_before_auth(
    client: AsyncClient, form_calls: list[int]
) -> None:
    # No session cookie at all: the length check runs before auth.
    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/documents",
        content=b"x" * 16,
        headers={
            "content-type": "multipart/form-data; boundary=zzz",
            "content-length": str(50 * 1024 * 1024),
        },
    )
    assert response.status_code == 413
    assert response.json()["error"]["message"] == MSG_TOO_LARGE
    assert form_calls == []


async def test_missing_content_length_is_rejected(
    client: AsyncClient, form_calls: list[int]
) -> None:
    async def _chunks() -> AsyncIterator[bytes]:
        yield b"--zzz\r\n"

    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/documents",
        content=_chunks(),
        headers={"content-type": "multipart/form-data; boundary=zzz"},
    )
    assert response.status_code == 411
    assert response.json()["error"]["code"] == "LENGTH_REQUIRED"
    assert form_calls == []


async def test_body_longer_than_declared_is_cut_off(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    stub_storage: StubS3,
) -> None:
    """The byte-counting guard: a body that runs past its Content-Length
    (or past the cap) is stopped while streaming."""
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    body = (
        b'--zzz\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
        + PDF_BYTES * 200
        + b"\r\n--zzz--\r\n"
    )
    response = await client.post(
        f"{BASE}/{draft_id}/documents",
        content=body,
        headers={"content-type": "multipart/form-data; boundary=zzz", "content-length": "200"},
    )
    assert response.status_code == 413
    assert stub_storage.keys() == []


async def test_one_file_per_upload(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    stub_storage: StubS3,
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    response = await client.post(
        f"{BASE}/{draft_id}/documents",
        files=[
            ("file", ("a.pdf", PDF_BYTES, "application/pdf")),
            ("file", ("b.png", PNG_BYTES, "image/png")),
        ],
        data={"doc_type": "pay_stub"},
    )
    assert response.status_code == 422
    assert stub_storage.keys() == []


async def test_missing_parts_are_422(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    stub_storage: StubS3,
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    no_file = await client.post(
        f"{BASE}/{draft_id}/documents", data={"doc_type": "pay_stub"}, files={"x": ("", b"")}
    )
    assert no_file.status_code == 422
    no_type = await client.post(
        f"{BASE}/{draft_id}/documents", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")}
    )
    assert no_type.status_code == 422
    assert stub_storage.keys() == []


async def test_document_cap_is_checked_before_reading(
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[Any]],
    stub_storage: StubS3,
    form_calls: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await make_borrower_session()
    draft_id = (await client.post(BASE)).json()["id"]
    monkeypatch.setattr(documents, "MAX_DOCUMENTS_PER_DRAFT", 1)
    first = await client.post(
        f"{BASE}/{draft_id}/documents",
        files={"file": ("a.pdf", PDF_BYTES, "application/pdf")},
        data={"doc_type": "pay_stub"},
    )
    assert first.status_code == 201
    form_calls.clear()

    second = await client.post(
        f"{BASE}/{draft_id}/documents",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")},
        data={"doc_type": "w2"},
    )
    assert second.status_code == 422
    assert form_calls == []
    assert len(stub_storage.keys()) == 1
    assert MAX_DOCUMENTS_PER_DRAFT == 20
