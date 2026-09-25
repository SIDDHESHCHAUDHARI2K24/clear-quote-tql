"""Shared Temporal client for API routes that start/signal
`ApplicationPipelineWorkflow` (spec.md CQ-011 "API").

A single cached `Client` per process, FastAPI-injectable via
`get_temporal_client`; `backend/app/features/applications/tests/
test_pipeline_endpoints.py` overrides this dependency to hand out a
`temporalio.testing.WorkflowEnvironment`'s own client instead of connecting
to a real Temporal server.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
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


TemporalProvider = Callable[[], Awaitable[Client]]


def get_temporal_provider(request: Request) -> TemporalProvider:
    """CQ-020 (plan.md Decision 23): a *lazy* `get_temporal_client`, for
    routes that only need Temporal now and then (`PUT /package` and `GET
    /send-status` ask it only while a send looks in flight), so they never
    connect to Temporal otherwise. Honours a test's
    `dependency_overrides[get_temporal_client]`."""
    provider: TemporalProvider = request.app.dependency_overrides.get(
        get_temporal_client, get_temporal_client
    )
    return provider
