"""Response shapes for the pipeline start/resume routes (spec.md CQ-011
"API"). Not otherwise pinned by spec — kept minimal."""

from __future__ import annotations

from pydantic import BaseModel


class PipelineStartResponse(BaseModel):
    workflow_id: str
    started: bool
    """`False` when a run already existed for this application (the
    endpoint is idempotent — a second call 200s without starting a second
    run, spec.md AC7)."""


class PipelineResumeResponse(BaseModel):
    workflow_id: str
    signaled: bool = True
