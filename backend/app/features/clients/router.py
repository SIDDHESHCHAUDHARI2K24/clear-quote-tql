"""`GET /clients` and `GET /clients/{id}` (spec.md CQ-026 "Backend")."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff
from app.core.db import get_db
from app.features.clients.schemas import ClientDetail, ClientListResponse
from app.features.clients.service import get_client_detail, list_clients

router = APIRouter(tags=["clients"])


@router.get("/clients", response_model=ClientListResponse)
async def get_clients(
    user: CurrentStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, description="Name or email, partial, case-insensitive"),
    lo_id: uuid.UUID | None = Query(
        default=None, description="Manager/Admin only; ignored for an LO's own request"
    ),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    has_active: bool | None = Query(default=None),
    sort: str = Query(default="-last_activity"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ClientListResponse:
    result = await list_clients(
        db,
        user,
        q=q,
        lo_id=lo_id,
        created_from=created_from,
        created_to=created_to,
        has_active=has_active,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return ClientListResponse(
        items=result.items, total=result.total, page=result.page, page_size=result.page_size
    )


@router.get("/clients/{client_id}", response_model=ClientDetail)
async def get_client(
    client_id: uuid.UUID,
    user: CurrentStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientDetail:
    return await get_client_detail(db, user, client_id)
