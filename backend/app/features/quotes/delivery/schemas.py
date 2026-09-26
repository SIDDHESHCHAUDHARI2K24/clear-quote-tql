"""CQ-020 send contract (plan.md "API contract"): what the LO console's Send
tab consumes to send a package, poll its progress and list sent versions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SendStatusValue = Literal["idle", "queued", "rendering", "emailing", "done", "failed"]
"""`idle` = never sent through the workflow. The Send tab maps
queued/rendering -> "Rendering letter", emailing -> "Emailing", done -> "Done"."""


class SendStarted(BaseModel):
    """`POST /packages/{id}/send` 202. A double click while a send is in
    flight returns the running send's `workflow_id` (nothing new starts)."""

    package_id: uuid.UUID
    workflow_id: str
    status: SendStatusValue


class SendStatus(BaseModel):
    """`GET /packages/{id}/send-status`, poll until `done` or `failed`."""

    package_id: uuid.UUID
    workflow_id: str | None
    status: SendStatusValue
    error: str | None
    """Why the send failed (`status == "failed"`), else `None`."""
    version: int | None
    """The version this send froze, once Freeze has run."""
    recipient_email: str | None
    """For the "Sent to {email}" toast."""
    sent_at: datetime | None


class SentVersion(BaseModel):
    """One row of the Send tab's "Sent versions" list (newest first)."""

    id: uuid.UUID
    version: int
    sent_at: datetime
    expires_at: datetime
    superseded: bool
    viewed_at: datetime | None
    report_url: str
    """The borrower's `/report/{token}` link (sign-in gated, H2)."""
    letter_url: str | None
    """API path of this version's PDF (`/api/v1/packages/{id}/letter.pdf?version=N`),
    `None` when no PDF was stored (versions seeded outside the workflow)."""
    outbox_email_id: uuid.UUID | None
    """For "Open in Outbox" (CQ-029's viewer); `None` for seeded versions."""
    email_status: Literal["queued", "sent", "failed"] | None
    recipient_email: str | None
