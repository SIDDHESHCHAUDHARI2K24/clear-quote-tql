"""Pydantic response models for the `/health` endpoint."""

from typing import Literal

from pydantic import BaseModel

CheckStatus = str
"""`"ok"` or `"error: <short reason>"`."""


class CheckResult(BaseModel):
    name: str
    status: CheckStatus


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckStatus]
