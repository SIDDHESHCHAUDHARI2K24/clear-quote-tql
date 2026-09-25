"""Local fixtures for `applications/tests/test_pipeline_endpoints.py`: a
time-skipping `temporalio.testing.WorkflowEnvironment` (no real Temporal
server needed in CI) whose client overrides `get_temporal_client` for the
`client` (httpx) fixture's app instance. No worker is registered here —
`POST .../pipeline/start` only needs the server to *accept* the start
request (spec.md AC7 tests start/resume idempotency, not full pipeline
execution)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

from app.workflows.client import get_temporal_client


@pytest_asyncio.fixture
async def temporal_test_env() -> AsyncIterator[WorkflowEnvironment]:
    env = await WorkflowEnvironment.start_time_skipping()
    yield env
    await env.shutdown()


@pytest_asyncio.fixture
async def temporal_client(temporal_test_env: WorkflowEnvironment) -> Client:
    return temporal_test_env.client


@pytest_asyncio.fixture(autouse=True)
async def override_temporal_client_dep(
    app: FastAPI, temporal_client: Client
) -> AsyncIterator[None]:
    async def _override() -> Client:
        return temporal_client

    app.dependency_overrides[get_temporal_client] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_temporal_client, None)
