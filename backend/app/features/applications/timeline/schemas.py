"""`GET /applications/{id}/activity` response shapes (spec.md "Timeline")."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ActivityActor(BaseModel):
    kind: Literal["system", "staff", "borrower"]
    name: str


class ActivityEventOut(BaseModel):
    id: uuid.UUID
    actor: ActivityActor
    type: str
    message: str
    """Human-readable sentence built from `type` + `payload` (plan.md decision 4)."""
    payload_summary: str | None
    """A short `key=value, ...` rendering of `payload`, for anyone who wants
    the raw detail without a JSON viewer."""
    at: datetime
