"""`CreditReportDTO`: the mock credit bureau response shape."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.integrations.credit.models import CreditPullType


class CreditReportDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    pull_type: CreditPullType
    experian_score: int | None
    equifax_score: int | None
    transunion_score: int | None
    middle_score: int
    tradelines: Any
