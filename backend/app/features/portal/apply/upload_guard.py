"""Bounds the draft-upload request body before anything reads it (plan.md
decision 26; review round 1, major 2).

A pure ASGI middleware, so it runs before routing, auth and multipart
parsing (which spools file parts to disk):

- no `Content-Length` -> 411 (a chunked body cannot be sized up front);
- `Content-Length` over the cap (10 MB file + multipart overhead) -> 413;
- while the app reads the body, a byte counter stops a body that runs past
  its declared length or the cap -> 413.

Every other request passes straight through.
"""

from __future__ import annotations

import re
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .documents import MAX_UPLOAD_BYTES, MSG_TOO_LARGE

MULTIPART_OVERHEAD_BYTES = 64 * 1024
"""Room for the boundaries, part headers and the `doc_type` field."""
MAX_UPLOAD_BODY_BYTES = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES

UPLOAD_PATH = re.compile(r"^/api/v1/portal/applications/[^/]+/documents/?$")


class _BodyTooLargeError(Exception):
    pass


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": {}}},
    )


class UploadBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        path: re.Pattern[str] = UPLOAD_PATH,
        max_body_bytes: int = MAX_UPLOAD_BODY_BYTES,
    ) -> None:
        self.app = app
        self.path = path
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not self.path.fullmatch(scope["path"])
        ):
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is None:
            await _error(411, "LENGTH_REQUIRED", "Content-Length is required.")(
                scope, receive, send
            )
            return
        try:
            length = int(declared)
        except ValueError:
            length = -1
        if length < 0:
            await _error(400, "BAD_REQUEST", "Invalid Content-Length.")(scope, receive, send)
            return
        if length > self.max_body_bytes:
            await _error(413, "FILE_TOO_LARGE", MSG_TOO_LARGE)(scope, receive, send)
            return

        received = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > length:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLargeError:
            if response_started:
                raise
            await _error(413, "FILE_TOO_LARGE", MSG_TOO_LARGE)(scope, _empty_receive, send)


async def _empty_receive() -> dict[str, Any]:
    return {"type": "http.disconnect"}
