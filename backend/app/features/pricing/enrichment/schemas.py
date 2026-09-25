"""Request/response schemas for the field-value override/revert routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.enums import FieldSource


class FieldValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    field_key: str
    value: dict | list | str | float | bool | None
    source: FieldSource
    source_ref: str | None
    overridden_by: uuid.UUID | None
    overridden_at: datetime | None


class FieldValueOverrideRequest(BaseModel):
    """Every overridable pricing field (spec.md's fixed 5-key list) is a
    currency or rate `Decimal`."""

    value: Decimal
