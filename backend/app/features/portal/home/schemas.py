"""`GET /api/v1/portal/me` request/response shapes (CQ-031 spec.md).

Every borrower-facing word here must stay in plain language — AC2 asserts
"attention", "flag" and "error" appear nowhere in this response, so no
field name or value below may spell out an internal `ApplicationStatus`
or verification vocabulary.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PortalStage(StrEnum):
    """Borrower-facing stage (spec.md's mapping table), plus `draft` for an
    open `application_drafts` row (CQ-032a) that has no `Application` yet."""

    APPLIED = "applied"
    IN_REVIEW = "in_review"
    PREAPPROVED = "preapproved"
    OPTION_SELECTED = "option_selected"
    CLOSED = "closed"
    DRAFT = "draft"


class PortalNextActionType(StrEnum):
    VIEW_REPORT = "view_report"
    CONTINUE_APPLICATION = "continue_application"
    AUTHORIZE_CREDIT_CHECK = "authorize_credit_check"
    NONE = "none"


class PortalNextAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: PortalNextActionType
    report_token: str | None = None
    """Set only when `type == view_report`."""
    consent_id: uuid.UUID | None = None
    """Set only when `type == authorize_credit_check`."""
    draft_id: uuid.UUID | None = None
    """Set only when `type == continue_application`."""


class PortalLoOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    phone: str | None
    email: str


class PortalApplicationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    stage: PortalStage
    label: str
    next_action: PortalNextAction
    secondary_report_token: str | None = None
    """Luis Romero's case (AC3): `option_selected` always gets
    `next_action.type = none`, but a "View your numbers" link still works
    when a sent version exists -- carried here, separate from
    `next_action`, so the frontend never has to infer it."""
    lo: PortalLoOut | None = None
    """`None` for a draft entry (no LO is assigned before CQ-032a submit)."""


class PortalHomeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    first_name: str
    email: str
    applications: list[PortalApplicationOut]
