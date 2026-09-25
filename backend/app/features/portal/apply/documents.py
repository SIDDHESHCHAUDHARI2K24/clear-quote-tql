"""Draft document uploads (CQ-032 AC7; plan.md decisions 19-20).

Before submit there is no application id, so an upload is stored under
`drafts/{draft_id}/documents/` and listed in the draft's
`data.income.documents`; submit copies it to
`applications/{application_id}/documents/` and creates the `documents`
row the LO's checklist reads.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast, get_args

from fastapi import Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import clock, storage
from app.core.errors import AppError, NotFoundError, ValidationAppError
from app.features.auth.models import BorrowerAccount

from .models import ApplicationDraft
from .schemas import DocType, DraftDocumentOut
from .service import _documents_of, _ensure_open, _store_data, _with_documents, get_owned_draft

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_DOCUMENTS_PER_DRAFT = 20
MAX_FORM_FIELDS = 4
DOC_TYPES: frozenset[str] = frozenset(get_args(DocType))
MSG_TOO_LARGE = "Files must be 10 MB or smaller."
MSG_BAD_TYPE = "Only PDF, JPG and PNG files are accepted."
MSG_ONE_FILE = "Upload one file at a time."

# extension -> (content type, accepted magic-byte prefixes)
_ALLOWED: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
}


class FileTooLargeError(AppError):
    code = "FILE_TOO_LARGE"
    status_code = 413


class UnsupportedFileTypeError(AppError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = 415


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _safe_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name[:200] or "document"


async def _open_owned_draft(
    db: AsyncSession, account: BorrowerAccount, draft_id: uuid.UUID, *, for_update: bool
) -> ApplicationDraft:
    draft = await get_owned_draft(db, account, draft_id, for_update=for_update)
    _ensure_open(draft)
    return draft


async def _read_limited(upload: UploadFile) -> bytes:
    """Reads at most one byte past the limit, so an oversized upload is
    rejected without buffering all of it."""
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileTooLargeError(MSG_TOO_LARGE)
    return data


def _check_room(draft: ApplicationDraft) -> list[dict[str, Any]]:
    """The draft's documents; 422 when it already holds the maximum."""
    documents = _documents_of(draft.data or {})
    if len(documents) >= MAX_DOCUMENTS_PER_DRAFT:
        raise ValidationAppError(f"You can upload up to {MAX_DOCUMENTS_PER_DRAFT} documents.")
    return documents


async def _parse_upload(request: Request) -> tuple[DocType, UploadFile]:
    """Parses the multipart body: exactly one `file` part and a `doc_type`
    field. Runs only after auth, ownership and the document cap passed;
    the body's size was already bounded by `UploadBodyLimitMiddleware`."""
    try:
        form = await request.form(max_files=1, max_fields=MAX_FORM_FIELDS)
    except StarletteHTTPException as exc:  # malformed multipart, too many parts
        raise ValidationAppError(MSG_ONE_FILE) from exc
    upload = form.get("file")
    if not isinstance(upload, StarletteUploadFile):
        raise ValidationAppError(
            "Choose a file to upload.", details={"field_errors": {"file": "required"}}
        )
    doc_type = form.get("doc_type")
    if doc_type not in DOC_TYPES:
        raise ValidationAppError(
            "Choose a document type.", details={"field_errors": {"doc_type": "invalid"}}
        )
    return cast(DocType, doc_type), cast(UploadFile, upload)


async def add_document(
    db: AsyncSession,
    account: BorrowerAccount,
    draft_id: uuid.UUID,
    request: Request,
) -> DraftDocumentOut:
    # Ownership, open state and the cap are checked before the body is read
    # (review round 1, minor 4), then again under the row lock.
    _check_room(await _open_owned_draft(db, account, draft_id, for_update=False))
    await db.commit()  # nothing pending: just no transaction open while the body streams in

    doc_type, upload = await _parse_upload(request)

    filename = _safe_filename(upload.filename or "")
    allowed = _ALLOWED.get(_extension(filename))
    if allowed is None:
        raise UnsupportedFileTypeError(MSG_BAD_TYPE)
    content_type, magics = allowed

    data = await _read_limited(upload)
    if not data:
        raise ValidationAppError("The file is empty.")
    if not any(data.startswith(magic) for magic in magics):
        raise UnsupportedFileTypeError(MSG_BAD_TYPE)

    draft = await _open_owned_draft(db, account, draft_id, for_update=True)
    documents = _check_room(draft)

    doc_id = uuid.uuid4()
    key = f"drafts/{draft.id}/documents/{doc_id}{_extension(filename)}"
    await storage.ensure_bucket()
    await storage.put_object(key, data, content_type)

    uploaded_at = clock.now()
    entry: dict[str, Any] = {
        "id": str(doc_id),
        "doc_type": doc_type,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(data),
        "uploaded_at": uploaded_at.isoformat(),
        "object_key": key,
    }
    await _store_data(db, draft, _with_documents(draft.data or {}, [*documents, entry]))
    await db.commit()
    return DraftDocumentOut(
        id=doc_id,
        doc_type=doc_type,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        uploaded_at=uploaded_at,
    )


async def remove_document(
    db: AsyncSession, account: BorrowerAccount, draft_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    draft = await _open_owned_draft(db, account, draft_id, for_update=True)
    documents = _documents_of(draft.data or {})
    match = next((d for d in documents if d.get("id") == str(document_id)), None)
    if match is None:
        raise NotFoundError("Document not found")
    remaining = [d for d in documents if d is not match]
    await _store_data(db, draft, _with_documents(draft.data or {}, remaining))
    await db.commit()
    try:
        await storage.delete_object(str(match["object_key"]))
    except Exception:
        logger.warning("Could not delete draft upload %s", match["object_key"], exc_info=True)
