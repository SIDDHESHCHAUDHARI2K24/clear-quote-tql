"""`GET /outbox`, `GET /outbox/{id}`, `GET /outbox/{id}/attachments/{key}`
(spec.md "Outbox"). Every route is staff-only (any role); scoping to what
that staff member may see happens in `service.py` (plan.md decision 2)."""

from __future__ import annotations

import mimetypes
import uuid
from collections.abc import AsyncIterator
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff
from app.core.db import get_db
from app.core.errors import NotFoundError
from app.core.pagination import Page
from app.core.storage import ObjectNotFoundError, astream_object
from app.features.notifications.outbox.schemas import EmailType, OutboxEmailDetail, OutboxEmailRow
from app.features.notifications.outbox.service import (
    get_attachment_key,
    get_outbox_email_detail,
    list_outbox,
)

router = APIRouter(tags=["outbox"])


@router.get("/outbox", response_model=Page[OutboxEmailRow])
async def list_outbox_emails(
    user: CurrentStaff,
    q: str | None = None,
    type: EmailType | None = Query(default=None),  # noqa: A002
    application_id: uuid.UUID | None = None,
    page: int | None = Query(default=1),
    page_size: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Page[OutboxEmailRow]:
    return await list_outbox(
        db, user, q=q, type=type, application_id=application_id, page=page, page_size=page_size
    )


@router.get("/outbox/{email_id}", response_model=OutboxEmailDetail)
async def get_outbox_email(
    email_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> OutboxEmailDetail:
    return await get_outbox_email_detail(db, user, email_id)


@router.get("/outbox/{email_id}/attachments/{key:path}")
async def download_attachment(
    email_id: uuid.UUID,
    key: str,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    resolved_key = await get_attachment_key(db, user, email_id, key)
    filename = resolved_key.rsplit("/", 1)[-1]
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # Code review finding: `stream_object` (sync) issues its GET on the
    # calling thread -- fine when *Starlette* calls it inside
    # `StreamingResponse`'s own threadpool, but here the route itself was
    # calling it directly, blocking the whole event loop for the GET's
    # round trip. `astream_object` runs the GET via `asyncio.to_thread`
    # instead. It's a lazy async generator, though, so nothing actually
    # happens until the first chunk is pulled -- and `StreamingResponse`
    # sends the response headers *before* pulling that first chunk. Pulling
    # one chunk here, before constructing the response, keeps a missing key
    # a clean 404 (no headers sent yet) instead of a 200 that aborts mid-
    # stream once `StreamingResponse` hits the same `ObjectNotFoundError`.
    chunks = astream_object(resolved_key)
    try:
        first_chunk = await anext(chunks, b"")
    except ObjectNotFoundError as exc:
        raise NotFoundError(f"Attachment not found: {resolved_key}") from exc

    async def _body() -> AsyncIterator[bytes]:
        if first_chunk:
            yield first_chunk
        async for chunk in chunks:
            yield chunk

    # RFC 5987 `filename*` (nit, review round 1): a non-ASCII attachment
    # filename (e.g. a borrower's accented name) survives instead of being
    # mangled by the plain `filename="..."` fallback most browsers still
    # need too. The ASCII fallback also escapes `\` and `"` (code review
    # round 2 -- an unescaped embedded `"` truncated the quoted-string
    # early, e.g. `filename="a"b.pdf"`).
    ascii_filename = filename.encode("ascii", "replace").decode("ascii")
    escaped_ascii_filename = ascii_filename.replace("\\", "\\\\").replace('"', '\\"')
    content_disposition = (
        f"attachment; filename=\"{escaped_ascii_filename}\"; filename*=UTF-8''{quote(filename)}"
    )

    return StreamingResponse(
        _body(),
        media_type=content_type,
        headers={"Content-Disposition": content_disposition},
    )
