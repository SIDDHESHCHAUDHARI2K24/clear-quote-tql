"""Local fixture for `admin/integrations/tests/`: writes `integration_calls`
rows directly (CQ-009's `record_call` shape) so tests don't need a real
mock adapter call."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.models import IntegrationCall


@pytest_asyncio.fixture
async def make_integration_call(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[IntegrationCall]]:
    async def _make(
        adapter: str,
        *,
        success: bool = True,
        latency_ms: int = 250,
        error_code: str | None = None,
        called_at: datetime | None = None,
    ) -> IntegrationCall:
        call = IntegrationCall(
            id=uuid.uuid4(),
            adapter=adapter,
            request_summary={},
            success=success,
            latency_ms=latency_ms,
            error_code=error_code,
            called_at=called_at or datetime.now(UTC),
        )
        db_session.add(call)
        await db_session.flush()
        return call

    return _make
