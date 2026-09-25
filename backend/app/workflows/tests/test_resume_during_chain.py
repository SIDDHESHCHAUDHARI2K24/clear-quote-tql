"""CQ-028a review minor 4: a `resume` signal that arrives while the pricing
chain is still running must not be lost.

Runs the real `ApplicationPipelineWorkflow` against stub activities (same
names) on its own task queue: the first `verify_application` sends the
signal itself and then fails, so the signal lands mid-chain. Before the
`p56-resume-reset` patch the workflow cleared the flag after the failed
chain and parked forever; now it resumes and reaches `priced`.
"""

from __future__ import annotations

import asyncio
import uuid

from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from app.core.enums import ApplicationSource
from app.features.pricing.enrichment.service import EnrichmentResult
from app.features.pricing.scenarios.service import PricingResult
from app.features.quotes.builder.service import QuoteSetResult
from app.workflows.activities import VerificationResult
from app.workflows.application_pipeline import ApplicationPipelineWorkflow


async def test_resume_signal_during_chain_is_not_lost(temporal_client: Client) -> None:
    workflow_id = f"resume-during-chain-{uuid.uuid4()}"
    task_queue = f"resume-during-chain-{uuid.uuid4()}"
    verify_calls = 0
    resumed_calls = 0

    @activity.defn(name="load_application_source")
    async def load_source(_application_id: str) -> str:
        return ApplicationSource.PORTAL.value

    @activity.defn(name="verify_application")
    async def verify(_application_id: str) -> VerificationResult:
        nonlocal verify_calls
        verify_calls += 1
        if verify_calls == 1:
            # The LO's fix lands (and the API signals) while verify runs.
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
        nonlocal resumed_calls
        resumed_calls += 1

    async with Worker(
        temporal_client,
        task_queue=task_queue,
        workflows=[ApplicationPipelineWorkflow],
        activities=[load_source, verify, enrich, validate, auto_price, draft, record_resumed],
    ):
        handle = await temporal_client.start_workflow(
            ApplicationPipelineWorkflow.run,
            str(uuid.uuid4()),
            id=workflow_id,
            task_queue=task_queue,
        )
        result = await asyncio.wait_for(handle.result(), timeout=15)

    assert result == "priced"
    assert verify_calls == 2
    assert resumed_calls == 1
