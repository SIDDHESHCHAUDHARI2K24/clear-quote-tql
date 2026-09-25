"""Request/response shapes for `GET /applications` (spec.md CQ-027
"Backend"). `ApplicationRow` is also the shared row shape CQ-026 (Clients,
E9) reuses for its own application tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.enums import ApplicationStatus
from app.core.pagination import Page

StrategyLabel = Literal["primary", "ltr", "str"]
"""The three-way filter/display value (spec.md's `strategy` parameter):
`Strategy` (`app.core.enums`) has only `ltr`/`str` -- `primary` means
`applications.strategy IS NULL` (Decision #4, plan.md)."""


class ApplicationRow(BaseModel):
    """One row of `GET /applications` (spec.md "Row"). Shared with CQ-026
    (E9) -- keep this shape stable; CQ-026 imports it directly rather than
    redefining it."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    client_name: str
    property_label: str | None
    """The subject address, or `"TBD · {metros}"`, or `None` when the
    application has no `properties` row at all (plan.md Decision #8)."""
    strategy: StrategyLabel
    purchase_price: Decimal | None
    status: ApplicationStatus
    flag_count: int
    """Count of this application's *unresolved* flags (spec.md "open flag
    count")."""
    lo_id: uuid.UUID
    lo_name: str
    updated_at: datetime


class ApplicationListResponse(Page[ApplicationRow]):
    """`GET /applications` response: `core/pagination.Page[ApplicationRow]`
    (`items`, `total`, `page`, `page_size`)."""


class LoOption(BaseModel):
    """One entry of `GET /applications/los` -- the frontend's "LO" `Select`
    for a Manager/Admin (spec.md "Frontend"). Nothing else in the backend
    exposes a role=lo user list yet, so this item owns it (small, scoped
    necessity -- plan.md)."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    full_name: str
