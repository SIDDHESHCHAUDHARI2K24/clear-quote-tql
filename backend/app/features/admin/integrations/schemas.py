"""`GET/PUT /admin/integrations` shapes (spec.md "Integration panel")."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AdapterStatus(BaseModel):
    adapter: str
    provider: str
    """The real vendor this mock emulates (system-design.md "Emulated
    integrations")."""
    last_call_at: datetime | None
    last_latency_ms: int | None
    last_result: str
    """`"ok"`, an `error_code` (e.g. `PROVIDER_UNAVAILABLE`), or
    `"never_called"` when no `integration_calls` row exists yet."""
    calls_last_hour: int
    force_failure: bool


class IntegrationsResponse(BaseModel):
    adapters: list[AdapterStatus]


class ForceFailureRequest(BaseModel):
    force_failure: bool
