"""Pydantic response models for the `/health` endpoint."""

from typing import Literal

from pydantic import BaseModel

CheckStatus = str
"""`"ok"` or `"error: <short reason>"`."""


class CheckResult(BaseModel):
    """One backing-service check's outcome; `service.py`'s `check_*`
    functions return these, and `run_health_checks` flattens them into
    `HealthReport.checks`'s pinned `dict[str, str]` shape."""

    name: str
    status: CheckStatus


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckStatus]
