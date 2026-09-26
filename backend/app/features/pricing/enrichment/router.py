"""Field-value override/revert routes (spec.md route table).

Each route takes the locks in the one order (applications/locking.py):
the application's quotes first (the override/revert marks them stale),
then the application (CQ-018 PR review minor 4: serialize with Quote
Builder writes). The override and its `field.edited`/`field.reverted`
activity event commit together, in one transaction under those locks
(PR #34 review m2): the service only flushes, `record_field_event` adds the
event and commits.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, get_scoped_application
from app.core.db import get_db
from app.features.applications.locking import lock_application, lock_application_quotes
from app.features.applications.models import Application
from app.features.applications.sections.events import record_field_event
from app.features.pricing.enrichment.schemas import FieldValueOverrideRequest, FieldValueRead
from app.features.pricing.enrichment.service import override_field_value, revert_field_value

router = APIRouter(tags=["pricing"])


@router.patch(
    "/applications/{application_id}/field-values/{field_key}", response_model=FieldValueRead
)
async def patch_field_value(
    application_id: uuid.UUID,
    field_key: str,
    request: FieldValueOverrideRequest,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    _application: Application = Depends(get_scoped_application),
) -> FieldValueRead:
    await lock_application_quotes(db, application_id)
    await lock_application(db, application_id)
    row = await override_field_value(
        db, application_id, field_key, request.value, user.id, commit=False
    )
    result = FieldValueRead.model_validate(row)
    # CQ-028a (AC7): activity event naming the field; commits both.
    await record_field_event(
        db, application_id, user_id=user.id, reverted=False, field_key=field_key
    )
    return result


@router.post(
    "/applications/{application_id}/field-values/{field_key}/revert",
    response_model=FieldValueRead,
)
async def revert_field_value_route(
    application_id: uuid.UUID,
    field_key: str,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    _application: Application = Depends(get_scoped_application),
) -> FieldValueRead:
    await lock_application_quotes(db, application_id)
    await lock_application(db, application_id)
    row = await revert_field_value(db, application_id, field_key, user.id, commit=False)
    result = FieldValueRead.model_validate(row)
    # CQ-028a (AC7): activity event naming the field; commits both.
    await record_field_event(
        db, application_id, user_id=user.id, reverted=True, field_key=field_key
    )
    return result
