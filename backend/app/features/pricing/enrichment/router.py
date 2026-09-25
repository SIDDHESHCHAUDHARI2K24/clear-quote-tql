"""Field-value override/revert routes (spec.md route table)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.features.pricing.enrichment.schemas import FieldValueOverrideRequest, FieldValueRead
from app.features.pricing.enrichment.service import override_field_value, revert_field_value
from app.features.pricing.scenarios.deps import get_current_lo_stub

router = APIRouter(tags=["pricing"])


@router.patch(
    "/applications/{application_id}/field-values/{field_key}", response_model=FieldValueRead
)
async def patch_field_value(
    application_id: uuid.UUID,
    field_key: str,
    request: FieldValueOverrideRequest,
    db: AsyncSession = Depends(get_db),
    lo_id: uuid.UUID = Depends(get_current_lo_stub),
) -> FieldValueRead:
    row = await override_field_value(db, application_id, field_key, request.value, lo_id)
    return FieldValueRead.model_validate(row)


@router.post(
    "/applications/{application_id}/field-values/{field_key}/revert",
    response_model=FieldValueRead,
)
async def revert_field_value_route(
    application_id: uuid.UUID,
    field_key: str,
    db: AsyncSession = Depends(get_db),
    lo_id: uuid.UUID = Depends(get_current_lo_stub),
) -> FieldValueRead:
    row = await revert_field_value(db, application_id, field_key)
    return FieldValueRead.model_validate(row)
