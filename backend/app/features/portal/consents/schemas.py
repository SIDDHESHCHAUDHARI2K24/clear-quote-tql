"""Portal hard-pull consent API shapes (CQ-033)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.features.borrower.consent.models import ConsentStatus

TYPED_NAME_MAX = 200
DECLINE_REASON_MAX = 1000


class ConsentLoOut(BaseModel):
    name: str
    email: str
    phone: str | None
    nmls: str | None


class ConsentTextOut(BaseModel):
    version: str
    body: str
    """The paragraphs above the checkbox."""
    authorization: str
    """The checkbox sentence ("I authorize ..."), part of the versioned text."""
    sha256: str
    """SHA-256 of the whole versioned text (`body` + blank line +
    `authorization`); echoed back as `text_sha256` on accept."""


class PortalConsentOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    status: ConsentStatus
    requested_at: datetime | None
    expires_at: datetime | None
    decided_at: datetime | None
    decline_reason: str | None
    borrower_name: str
    """The name the typed signature must match (case-insensitive)."""
    lo: ConsentLoOut | None
    text: ConsentTextOut
    fico_after_pull: int | None
    """The representative FICO once the hard pull is done, else null."""


class ConsentAcceptRequest(BaseModel):
    typed_name: str = Field(min_length=1, max_length=TYPED_NAME_MAX)
    text_version: str = Field(min_length=1, max_length=64)
    """The consent text version the borrower was shown."""
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    """`text.sha256` from the GET the borrower read; a mismatch with the
    version being accepted is 409 `CONSENT_TEXT_CHANGED` (hardening m2)."""


class ConsentDeclineRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=DECLINE_REASON_MAX)
