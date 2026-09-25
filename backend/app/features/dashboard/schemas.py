"""Request/response shapes for `GET /api/v1/dashboard` (CQ-025 spec.md)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import ApplicationStatus


class DashboardTiles(BaseModel):
    """One count per spec.md's tile table, all scoped by role/`lo_id`."""

    model_config = ConfigDict(frozen=True)

    clients: int
    applications: int
    pre_approvals_sent: int
    with_property: int
    awaiting_review: int
    needs_attention: int
    stale_quotes: int


class AttentionItem(BaseModel):
    """One row of the "Needs your attention" list: NeedsAttention, Inquiry
    or OptionSelected, oldest status change first."""

    model_config = ConfigDict(frozen=True)

    application_id: uuid.UUID
    client_name: str
    status: ApplicationStatus
    reason: str
    """The flag message (NeedsAttention), inquiry note excerpt (Inquiry) or
    selected option label (OptionSelected)."""
    age_days: int
    """Days since `Application.updated_at` (the status-change proxy)."""


class StaleItem(BaseModel):
    """One row of the "Going stale" list: the recommended quote or latest
    sent version is older than 21 days."""

    model_config = ConfigDict(frozen=True)

    application_id: uuid.UUID
    client_name: str
    days_old: int


class ActivityItem(BaseModel):
    """One row of the "Recent activity" feed."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    actor: str
    """A resolved display label ("System" or the staff user's `full_name`),
    not the raw `ActivityEvent.actor` value stored on the row."""
    type: str
    application_id: uuid.UUID
    client_name: str
    at: datetime


class LoOption(BaseModel):
    """One entry in the Manager/Admin LO filter `Select`."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    full_name: str


class DashboardResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    tiles: DashboardTiles
    attention: list[AttentionItem]
    stale: list[StaleItem]
    activity: list[ActivityItem]
    los: list[LoOption] | None
    """Every `lo`-role user, for the Manager/Admin filter `Select`. `null`
    for an LO caller (they have nothing to filter — it's always their own
    files)."""
