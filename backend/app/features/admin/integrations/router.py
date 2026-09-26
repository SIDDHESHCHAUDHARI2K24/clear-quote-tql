"""`GET/PUT /admin/integrations` (spec.md "Integration panel"). Admin only
(`require_roles`, a straight 403 for anyone else, per plan.md E16's own
carve-out for admin-only routes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.db import get_db
from app.core.enums import UserRole
from app.features.admin.integrations.schemas import (
    AdapterStatus,
    ForceFailureRequest,
    IntegrationsResponse,
)
from app.features.admin.integrations.service import (
    list_integration_status,
    set_adapter_force_failure,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/integrations", response_model=IntegrationsResponse)
async def get_integrations(
    _admin: object = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> IntegrationsResponse:
    return IntegrationsResponse(adapters=await list_integration_status(db))


@router.put("/integrations/{adapter}", response_model=AdapterStatus)
async def put_integration(
    adapter: str,
    request: ForceFailureRequest,
    _admin: object = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdapterStatus:
    # No DB write here: the toggle lives in Valkey
    # (`integrations/common/failure_toggle.py`), not Postgres.
    return await set_adapter_force_failure(db, adapter, request.force_failure)
