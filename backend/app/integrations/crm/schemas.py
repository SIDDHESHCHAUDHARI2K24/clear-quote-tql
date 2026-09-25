"""`CrmEventDTO`: the mock CRM's write acknowledgement shape."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CrmEventDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    contact_id: str
    event_type: str
    at: datetime
