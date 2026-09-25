"""`GET /applications` (spec.md CQ-027 "Backend")."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, require_roles
from app.core.db import get_db
from app.core.enums import UserRole
from app.features.applications.listing.schemas import ApplicationListResponse, LoOption
from app.features.applications.listing.service import list_applications, list_lo_options
from app.features.auth.models import User

router = APIRouter(tags=["applications"])


@router.get("/applications", response_model=ApplicationListResponse)
async def get_applications(
    user: CurrentStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(
        default=None, description="Client name or email, partial, case-insensitive"
    ),
    lo_id: uuid.UUID | None = Query(
        default=None, description="Manager/Admin only; ignored for an LO's own request"
    ),
    status: str | None = Query(
        default=None, description="Comma list of status labels, plus the alias sent_or_later"
    ),
    strategy: str | None = Query(default=None, description="Comma list of primary, ltr, str"),
    amount_min: Decimal | None = Query(default=None),
    amount_max: Decimal | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    has_property: bool | None = Query(default=None),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    sort: str = Query(default="-updated_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ApplicationListResponse:
    result = await list_applications(
        db,
        user,
        q=q,
        lo_id=lo_id,
        status=status,
        strategy=strategy,
        amount_min=amount_min,
        amount_max=amount_max,
        state=state,
        has_property=has_property,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return ApplicationListResponse(
        items=result.items, total=result.total, page=result.page, page_size=result.page_size
    )


@router.get("/applications/los", response_model=list[LoOption])
async def get_lo_options(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_roles(UserRole.MANAGER, UserRole.ADMIN))],
) -> list[LoOption]:
    """Backs the frontend's LO `Select` (spec.md "Frontend", Manager/Admin
    only) -- 403s for an LO (E16), same as every other admin-scoped route."""
    return await list_lo_options(db)
