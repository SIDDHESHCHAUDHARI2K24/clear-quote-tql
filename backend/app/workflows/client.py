"""Shared Temporal client for API routes that start/signal
`ApplicationPipelineWorkflow` (spec.md CQ-011 "API").

A single cached `Client` per process, FastAPI-injectable via
`get_temporal_client`; `backend/app/features/applications/tests/
test_pipeline_endpoints.py` overrides this dependency to hand out a
`temporalio.testing.WorkflowEnvironment`'s own client instead of connecting
to a real Temporal server.
"""

from __future__ import annotations

from temporalio.client import Client

from app.core.config import get_settings

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = await Client.connect(
            settings.temporal_address, namespace=settings.temporal_namespace
        )
    return _client
