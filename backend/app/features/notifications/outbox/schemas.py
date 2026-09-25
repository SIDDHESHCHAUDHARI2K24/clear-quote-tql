"""`GET /outbox`, `GET /outbox/{id}` response shapes (spec.md "Outbox")."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.features.notifications.outbox.models import EmailStatus

# Single source of truth: must match `service.py`'s `_TYPE_SUBJECT_RULES`
# keys plus `"other"` (`KNOWN_EMAIL_TYPES`). A `Literal` here (rather than
# `str`) makes an unknown `?type=` a 422, not a silent empty result (code
# review round 1, minor 5).
EmailType = Literal["otp", "borrower_action", "quote_sent", "other"]


class OutboxEmailRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    to_email: str
    subject: str
    type: str
    """Derived from the subject (plan.md decision 1) -- `outbox_emails` has
    no `type` column."""
    status: EmailStatus
    application_id: uuid.UUID | None
    client_name: str | None
    """`None` when `application_id` is `None` (a support-inbox-style email
    with no application)."""
    sent_at: datetime | None
    """`updated_at` when `status == SENT`, else `None`."""
    created_at: datetime


class AttachmentOut(BaseModel):
    key: str
    filename: str


class OutboxEmailDetail(OutboxEmailRow):
    html: str
    attachments: list[AttachmentOut]
