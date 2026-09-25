"""Shared constants for `ApplicationPipelineWorkflow` (spec.md CQ-011).

Decision (plan.md #6): `APPLICATION_PIPELINE_TASK_QUEUE` reads
`get_settings().temporal_task_queue` rather than hardcoding a second,
divergent literal default — `Settings` (CQ-002/003) already owns
`TEMPORAL_TASK_QUEUE` (`.env.example`/CI pin it to `clear-quote-pipeline`),
so this stays "overridable via env `TEMPORAL_TASK_QUEUE`" per spec without
introducing a competing default string.
"""

from __future__ import annotations

from app.core.config import get_settings

APPLICATION_PIPELINE_TASK_QUEUE = get_settings().temporal_task_queue


def application_workflow_id(application_id: str) -> str:
    """Workflow id convention (spec.md Contracts): one run per application,
    ever."""
    return f"application-{application_id}"
