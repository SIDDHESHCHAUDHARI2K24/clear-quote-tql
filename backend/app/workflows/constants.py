"""Shared constants for `ApplicationPipelineWorkflow` (spec.md CQ-011).

Decision (plan.md #6): `APPLICATION_PIPELINE_TASK_QUEUE` reads
`get_settings().temporal_task_queue` rather than hardcoding a second,
divergent literal default — `Settings` (CQ-002/003) already owns
`TEMPORAL_TASK_QUEUE` (`.env.example`/CI pin it to `clear-quote-pipeline`),
so this stays "overridable via env `TEMPORAL_TASK_QUEUE`" per spec without
introducing a competing default string.
"""

from __future__ import annotations

import enum

from app.core.config import get_settings
from app.core.enums import ApplicationStatus

APPLICATION_PIPELINE_TASK_QUEUE = get_settings().temporal_task_queue


def application_workflow_id(application_id: str) -> str:
    """Workflow id convention (spec.md Contracts): one run per application,
    ever."""
    return f"application-{application_id}"


def send_workflow_id(package_id: str, attempt: str) -> str:
    """CQ-020 (plan.md Decision 9): one `SendQuotePackageWorkflow` run per
    `POST /packages/{id}/send`; `attempt` is a fresh uuid minted under the
    package lock. The id is every send activity's idempotency key."""
    return f"send-package-{package_id}-{attempt}"


class PipelineStage(enum.StrEnum):
    """CQ-016 (phase-p3-p4-plan.md D7): the six running-stage names an
    `ApplicationPipelineWorkflow` activity writes to `applications.
    last_pipeline_stage` when it starts doing work, so the workspace
    summary (CQ-016) can poll pipeline progress without a Temporal round
    trip. Order matches the pipeline chain in `application_pipeline.py`.

    There is deliberately no `STOPPED`/`DONE` member here: on a terminal
    outcome (the chain stops at `needs_attention`, or reaches `priced`),
    `activities.py` overwrites `last_pipeline_stage` with that
    `ApplicationStatus` *value string* instead of a 7th stage name --
    reusing the status vocabulary rather than inventing a parallel one.
    `is_pipeline_stage_terminal` below is the single place that encodes
    what counts as terminal; the frontend polling logic
    (`apps/lo-console/src/features/workspace/pipeline.ts`) mirrors it.
    """

    IMPORTING = "importing"
    VERIFYING = "verifying"
    ENRICHING = "enriching"
    VALIDATING = "validating"
    PRICING = "pricing"
    DRAFTING_QUOTES = "drafting_quotes"


TERMINAL_PIPELINE_STAGE_VALUES = frozenset(
    {ApplicationStatus.NEEDS_ATTENTION.value, ApplicationStatus.PRICED.value}
)


def is_pipeline_stage_terminal(stage: str | None) -> bool:
    """`True` for `None` (never started) or one of the two terminal status
    strings `activities.py` writes when the chain stops or finishes."""
    return stage is None or stage in TERMINAL_PIPELINE_STAGE_VALUES
