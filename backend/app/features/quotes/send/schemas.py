"""Send tab API shapes (CQ-019)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

LO_NOTE_MAX = 500


class PackageRead(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    quote_ids: list[uuid.UUID]
    """In the LO's order; the report puts the recommended option first."""
    recommended_quote_id: uuid.UUID | None
    recommendation_text: str | None
    """Pre-drafted by the server from the recommended quote (read-only)."""
    lo_note: str | None
    recipient_email: str | None
    """The borrower's email, shown in the Send confirm dialog."""
    attachments: list[str]
    """What the send email will carry (the confirm dialog lists them)."""
    sent_at: datetime | None
    updated_at: datetime


class PackageUpdate(BaseModel):
    quote_ids: list[uuid.UUID] = Field(max_length=3)
    recommended_quote_id: uuid.UUID | None = None
    lo_note: str | None = Field(default=None, max_length=LO_NOTE_MAX)


class ReadinessBlocker(BaseModel):
    code: str
    message: str
    tab: str
    """The workspace tab slug that fixes it (`pricing`, `borrowers`, ...)."""


class PackageReadiness(BaseModel):
    ready: bool
    blockers: list[ReadinessBlocker]
