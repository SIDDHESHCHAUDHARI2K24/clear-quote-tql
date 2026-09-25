"""`POST /api/v1/portal/reports/{token}/actions` request/response shapes
(CQ-024 spec.md)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ApplicationStatus


class BorrowerActionType(StrEnum):
    MOVE_FORWARD = "move_forward"
    ASK_OTHER = "ask_other"
    ASK_UPDATED = "ask_updated"


class PortalReportActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: BorrowerActionType
    quote_id: str | None = None
    """Required for `move_forward`; optional context for `ask_other`
    (the option the borrower was viewing); ignored for `ask_updated`."""
    message: str | None = Field(default=None, max_length=500)
    """Required (1-500 chars) for `ask_other`; optional for `ask_updated`;
    ignored for `move_forward`."""


class PortalReportActionState(BaseModel):
    """The "current state" a 409 (or a success) reports back, so the
    frontend can reconcile without guessing (spec.md: "Anything not
    allowed returns 409 with the current state")."""

    model_config = ConfigDict(frozen=True)

    status: ApplicationStatus
    borrower_action: dict[str, str | None] | None


class PortalReportActionResponse(PortalReportActionState):
    at: datetime
