"""`POST /api/v1/admin/jobs/stale-check` response (CQ-030 AC7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class StaleCheckResponse(BaseModel):
    """The counts one `mark_stale` run changed. Every count is zero on a
    repeat run."""

    ran_at: datetime
    """The injected `now` (`core/clock.now()`, honours `CLOCK_NOW`)."""
    quotes_marked_stale: int
    versions_expired: int
    applications_marked_stale: int
    application_ids: list[uuid.UUID]
