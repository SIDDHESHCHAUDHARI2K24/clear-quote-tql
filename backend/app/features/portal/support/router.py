"""`POST /api/v1/portal/support` (CQ-034 spec.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentBorrower
from app.core.db import get_db
from app.core.valkey import get_valkey

from . import service
from .schemas import SupportRequestCreate, SupportRequestResponse

router = APIRouter(tags=["portal-support"])


@router.post("/portal/support", response_model=SupportRequestResponse)
async def submit_support(
    request: SupportRequestCreate,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> SupportRequestResponse:
    return await service.submit_support_request(db, valkey, borrower=borrower, request=request)
