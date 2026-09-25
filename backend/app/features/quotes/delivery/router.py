"""CQ-020 send routes. Staff session required; an out-of-scope package is a
404 (Decision #11 / D6 -- AC7's 403 is logged as a deviation, plan.md
Decision 1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client as TemporalClient

from app.core.auth import CurrentStaff
from app.core.db import get_db
from app.features.quotes.delivery.schemas import SendStarted, SendStatus, SentVersion
from app.features.quotes.delivery.service import letter_pdf, list_versions, send_status, start_send
from app.features.quotes.send.service import get_scoped_package
from app.workflows.client import get_temporal_client

router = APIRouter(tags=["send"])


@router.post(
    "/packages/{package_id}/send",
    response_model=SendStarted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "PACKAGE_NOT_READY; `details.blockers` lists why"}},
)
async def post_send(
    package_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    temporal: TemporalClient = Depends(get_temporal_client),
) -> SendStarted:
    package = await get_scoped_package(db, package_id, user)
    return await start_send(db, package, temporal)


@router.get("/packages/{package_id}/send-status", response_model=SendStatus)
async def get_send_status(
    package_id: uuid.UUID, user: CurrentStaff, db: AsyncSession = Depends(get_db)
) -> SendStatus:
    package = await get_scoped_package(db, package_id, user)
    return await send_status(db, package)


@router.get("/packages/{package_id}/versions", response_model=list[SentVersion])
async def get_versions(
    package_id: uuid.UUID, user: CurrentStaff, db: AsyncSession = Depends(get_db)
) -> list[SentVersion]:
    package = await get_scoped_package(db, package_id, user)
    return await list_versions(db, package)


@router.get(
    "/packages/{package_id}/letter.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_letter_pdf(
    package_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    version: int | None = Query(default=None, ge=1),
) -> Response:
    package = await get_scoped_package(db, package_id, user)
    pdf, number = await letter_pdf(db, package, version)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="preapproval-letter-v{number}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )
