"""Request/response shapes for the workspace summary + status routes
(spec.md CQ-016 "Backend (owned by this item)")."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.enums import ApplicationStatus, ApplicationTab, Occupancy, Strategy

TabStateValue = Literal["ok", "flagged", "pending"]


class LocationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    city: str | None
    state: str | None
    zip: str | None


class TabStateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    tab: ApplicationTab
    state: TabStateValue
    flag_count: int


class ApplicationSummaryResponse(BaseModel):
    """`GET /applications/{id}/summary` (spec.md). Also the response shape
    for `PATCH /applications/{id}/status` (plan.md decision #9) so the LO
    console header/status pill refresh from one response."""

    model_config = ConfigDict(frozen=True)

    application_id: uuid.UUID
    client_name: str
    status: ApplicationStatus
    last_pipeline_stage: str | None
    occupancy: Occupancy | None
    strategy: Strategy | None
    program: str | None
    location: LocationResponse | None
    purchasing_power: Decimal | None
    """The purchase price used by the engine for the application's current
    scenario (plan.md decision #3) -- `null` before any scenario exists."""
    down_payment_pct: Decimal | None
    down_payment_amount: Decimal | None
    ppp_years: int | None
    """Prepayment penalty term in years; only meaningful for investment
    loans (spec.md AC2 -- primary shows no PPP field at all)."""
    note_rate: Decimal | None
    """`null` until `applications.recommended_quote_id` is set (spec.md AC3)."""
    tabs: list[TabStateResponse]
    default_tab: ApplicationTab


class StatusPatchRequest(BaseModel):
    """spec.md: "accepts only Withdrawn or Closed ... any other value
    returns 422" -- the `Literal` does that natively via Pydantic/FastAPI
    request validation, no extra code needed (plan.md decision #8)."""

    status: Literal[ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED]
    reason: str | None = None
