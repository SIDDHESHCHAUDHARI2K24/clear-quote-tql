"""Apply wizard API (CQ-032a). `{draft_id}` is always the borrower's draft
id: there is no application until submit (plan.md decision 1). Every route
404s for a draft the signed-in borrower does not own (decision 2)."""

from __future__ import annotations

import uuid
from typing import Any, get_args

from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentBorrower
from app.core.db import get_db
from app.core.valkey import get_valkey
from app.features.auth.common import client_ip
from app.workflows.client import get_temporal_client

from . import documents, service
from .schemas import (
    ApplyDraftOut,
    DocType,
    DraftDocumentOut,
    DraftPatchRequest,
    DraftPatchResponse,
    MetrosOut,
    SubmitResponse,
)

router = APIRouter(prefix="/portal/applications", tags=["portal-apply"])


def temporal_client_factory() -> service.TemporalClientFactory:
    """The Temporal client is resolved lazily inside submit, so a Temporal
    outage cannot fail the submit itself (plan.md #17). Tests override
    this dependency."""
    return get_temporal_client


@router.post("", response_model=ApplyDraftOut)
async def create_or_get_draft(
    borrower: CurrentBorrower, db: AsyncSession = Depends(get_db)
) -> ApplyDraftOut:
    """Creates the borrower's draft, or returns the open one."""
    draft = await service.get_or_create_draft(db, borrower)
    return await service.draft_out(db, draft, borrower)


@router.get("/metros", response_model=MetrosOut)
async def list_metros(_: CurrentBorrower, db: AsyncSession = Depends(get_db)) -> MetrosOut:
    """States and their metros for tab 2's picker (decision 28). Declared
    before `/{draft_id}` so `metros` is never read as a draft id."""
    return await service.metros_out(db)


@router.get("/{draft_id}", response_model=ApplyDraftOut)
async def get_draft(
    draft_id: uuid.UUID, borrower: CurrentBorrower, db: AsyncSession = Depends(get_db)
) -> ApplyDraftOut:
    draft = await service.get_owned_draft(db, borrower, draft_id)
    return await service.draft_out(db, draft, borrower)


@router.patch("/{draft_id}/draft", response_model=DraftPatchResponse)
async def autosave_tab(
    draft_id: uuid.UUID,
    body: DraftPatchRequest,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> DraftPatchResponse:
    """Saves one tab and returns its validation errors (never blocks)."""
    return await service.save_tab(db, borrower, draft_id, body.tab, body.data)


@router.post("/{draft_id}/submit", response_model=SubmitResponse)
async def submit_application(
    draft_id: uuid.UUID,
    request: Request,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
    client_factory: service.TemporalClientFactory = Depends(temporal_client_factory),
    valkey: Redis = Depends(get_valkey),
) -> SubmitResponse:
    return await service.submit(
        db,
        borrower,
        draft_id,
        client_factory=client_factory,
        valkey=valkey,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


_UPLOAD_BODY_SCHEMA: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "title": "DraftDocumentUpload",
                    "required": ["file", "doc_type"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "title": "File",
                            "description": "PDF, JPG or PNG, 10 MB at most.",
                        },
                        "doc_type": {
                            "type": "string",
                            "enum": list(get_args(DocType)),
                            "title": "Doc Type",
                        },
                    },
                }
            }
        },
    }
}


@router.post(
    "/{draft_id}/documents",
    response_model=DraftDocumentOut,
    status_code=201,
    openapi_extra=_UPLOAD_BODY_SCHEMA,
)
async def upload_document(
    draft_id: uuid.UUID,
    request: Request,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> DraftDocumentOut:
    """PDF, JPG or PNG, 10 MB at most (AC7). The multipart body is parsed
    by hand, only after auth, ownership and the document cap pass
    (decision 26); `UploadBodyLimitMiddleware` has already bounded its
    size (411 without `Content-Length`, 413 over the cap)."""
    try:
        return await documents.add_document(db, borrower, draft_id, request)
    finally:
        await request.close()  # closes (and deletes) any spooled file part


@router.delete("/{draft_id}/documents/{document_id}", status_code=204)
async def delete_document(
    draft_id: uuid.UUID,
    document_id: uuid.UUID,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await documents.remove_document(db, borrower, draft_id, document_id)
    return Response(status_code=204)
