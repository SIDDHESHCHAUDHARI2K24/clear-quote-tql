"""CQ-028a lock hardening, minor 5a: a history recorded before the
`p56-resume-reset` patch replays against the current workflow.

The history is recorded with the real `ApplicationPipelineWorkflow` on an
unsandboxed worker while `workflow.patched` answers False for the patch id,
which is exactly the pre-patch code path (no marker, flag cleared after a
failed chain). A `resume` signal lands mid-chain, is lost the old way, and
a later signal finishes the run. `Replayer` then replays that history
against the current (patched) workflow: it must not raise a
nondeterminism error.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import activity, workflow
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

from app.core.enums import ApplicationSource
from app.features.pricing.enrichment.service import EnrichmentResult
from app.features.pricing.scenarios.service import PricingResult
from app.features.quotes.builder.service import QuoteSetResult
from app.workflows.activities import VerificationResult
from app.workflows.application_pipeline import (
    RESUME_RESET_PATCH_ID,
    ApplicationPipelineWorkflow,
)


async def test_pre_patch_history_replays_against_current_workflow(
    temporal_client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow_id = f"resume-reset-replay-{uuid.uuid4()}"
    task_queue = f"resume-reset-replay-{uuid.uuid4()}"
    verify_calls = 0

    @activity.defn(name="load_application_source")
    async def load_source(_application_id: str) -> str:
        return ApplicationSource.PORTAL.value

    @activity.defn(name="verify_application")
    async def verify(_application_id: str) -> VerificationResult:
        nonlocal verify_calls
        verify_calls += 1
        if verify_calls == 1:
            # Lands mid-chain; the pre-patch code loses it.
            await temporal_client.get_workflow_handle(workflow_id).signal(
                ApplicationPipelineWorkflow.resume
            )
            return VerificationResult(rule_results=[], passed=False)
        return VerificationResult(rule_results=[], passed=True)

    @activity.defn(name="enrich_application")
    async def enrich(_application_id: str) -> EnrichmentResult:
        return EnrichmentResult()

    @activity.defn(name="validate_pricing_inputs")
    async def validate(_application_id: str) -> bool:
        return True

    @activity.defn(name="auto_price_application")
    async def auto_price(_application_id: str) -> PricingResult:
        return PricingResult(scenario_ids=[], quote_ids=[])

    @activity.defn(name="draft_quote_set")
    async def draft(_application_id: str, _pricing: PricingResult) -> QuoteSetResult:
        return QuoteSetResult(quote_ids=[])

    @activity.defn(name="record_pipeline_resumed")
    async def record_resumed(_application_id: str) -> None:
        return None

    real_patched = workflow.patched

    def _pre_patch(patch_id: str) -> bool:
        return False if patch_id == RESUME_RESET_PATCH_ID else real_patched(patch_id)

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "patched", _pre_patch)
        async with Worker(
            temporal_client,
            task_queue=task_queue,
            workflows=[ApplicationPipelineWorkflow],
            activities=[load_source, verify, enrich, validate, auto_price, draft, record_resumed],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await temporal_client.start_workflow(
                ApplicationPipelineWorkflow.run,
                str(uuid.uuid4()),
                id=workflow_id,
                task_queue=task_queue,
            )
            # The mid-chain signal was lost (old behaviour): keep signalling
            # (idempotent) until the parked run resumes and finishes. Polls
            # `describe`, not `result()`, which would let the time-skipping
            # server skip past the parked run's execution timeout.
            for _ in range(150):
                if (await handle.describe()).status is not WorkflowExecutionStatus.RUNNING:
                    break
                if verify_calls >= 1:
                    await handle.signal(ApplicationPipelineWorkflow.resume)
                await asyncio.sleep(0.1)
            result = await asyncio.wait_for(handle.result(), timeout=15)

    assert result == "priced"
    assert verify_calls == 2
    history = await handle.fetch_history()
    # Recorded pre-patch: no marker for the reset patch, but a resume loop.
    history_json = history.to_json()
    assert RESUME_RESET_PATCH_ID not in history_json
    assert "record_pipeline_resumed" in history_json

    await Replayer(workflows=[ApplicationPipelineWorkflow]).replay_workflow(history)
