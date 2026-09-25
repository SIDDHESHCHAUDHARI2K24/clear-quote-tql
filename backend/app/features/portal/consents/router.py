"""`/api/v1/portal/consents/{id}` (CQ-033 spec.md): read, accept, decline."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentBorrower
from app.core.db import get_db
from app.features.auth.common import client_ip

from . import service
from .schemas import ConsentAcceptRequest, ConsentDeclineRequest, PortalConsentOut

router = APIRouter(prefix="/portal/consents", tags=["portal-consents"])


@router.get("/{consent_id}", response_model=PortalConsentOut)
async def get_consent(
    consent_id: uuid.UUID,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> PortalConsentOut:
    return await service.get_consent(db, borrower=borrower, consent_id=consent_id)


@router.post("/{consent_id}/accept", response_model=PortalConsentOut)
async def accept_consent(
    consent_id: uuid.UUID,
    body: ConsentAcceptRequest,
    request: Request,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> PortalConsentOut:
    return await service.accept_consent(
        db,
        borrower=borrower,
        consent_id=consent_id,
        typed_name=body.typed_name,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/{consent_id}/decline", response_model=PortalConsentOut)
async def decline_consent(
    consent_id: uuid.UUID,
    body: ConsentDeclineRequest,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> PortalConsentOut:
    return await service.decline_consent(
        db, borrower=borrower, consent_id=consent_id, reason=body.reason
    )
