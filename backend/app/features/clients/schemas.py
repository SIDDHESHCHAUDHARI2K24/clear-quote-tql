"""Request/response shapes for `GET /clients` and `GET /clients/{id}`
(spec.md CQ-026 "Backend")."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.enums import ApplicationStatus
from app.core.pagination import Page
from app.features.applications.listing.schemas import ApplicationRow
from app.features.applications.timeline.schemas import ActivityEventOut

SentVersionStatus = Literal[
    "sent",
    "viewed",
    "expired",
    "superseded",
    "option_selected",
    "move_forward",
    "ask_other",
    "ask_updated",
    "inquiry",
]
"""plan.md Decision 9: derived, not stored -- see `service._version_status`."""


class ClientRow(BaseModel):
    """One row of `GET /clients` (spec.md "Rows")."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    name: str
    email: str
    phone: str | None
    lo_id: uuid.UUID
    lo_name: str
    application_count: int
    active_status: ApplicationStatus | None
    """The status of the client's most-recently-updated non-terminal
    application, or `None` when they have none (plan.md Decision 3)."""
    last_activity: datetime | None
    """`MAX(activity_events.at)` across every application the client has
    (plan.md Decision 5), or `None` when there's been none yet."""


class ClientListResponse(Page[ClientRow]):
    """`GET /clients` response: `core/pagination.Page[ClientRow]`."""


class ClientSentVersion(BaseModel):
    """One row of a client's "Quotes sent" section (spec.md "Backend"):
    one `quote_package_versions` row, across every application the client
    has."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    application_id: uuid.UUID
    version: int
    sent_at: datetime
    recommended_option_label: str | None
    """From the frozen snapshot's `options[]` (plan.md Decision 10)."""
    status: SentVersionStatus
    report_link: str
    """The full borrower-portal report URL (`{portal_base_url}/report/
    {token}`, plan.md Decision 11) -- built from `core.config.settings.
    portal_base_url`, same as `applications/sections/credit.py`'s
    consent-request link, since the LO console and borrower portal are
    separate origins."""


class ClientDetail(BaseModel):
    """`GET /clients/{id}` response (spec.md "Backend")."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    name: str
    email: str
    phone: str | None
    lo_id: uuid.UUID
    lo_name: str
    created_at: datetime
    applications: list[ApplicationRow]
    """Same row shape CQ-027's list uses (E9)."""
    sent_versions: list[ClientSentVersion]
    activity: list[ActivityEventOut]
    """The merged timeline across every application, latest 50, newest
    first (plan.md Decision 7)."""
