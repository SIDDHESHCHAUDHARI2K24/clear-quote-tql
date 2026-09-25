"""Writes one `integration_calls` row per mock call, success or failure.

**Decision** (plan.md #2, deviating from spec.md's shorthand signature):
`record_call` takes a leading `session: AsyncSession` argument. CQ-004's
`app.core.db` module-level `engine`/`AsyncSessionLocal` is permanently bound
to `Settings.database_url`, a different (and in CI, non-existent -- CI's
Postgres service only creates `cq_test`) database from `TEST_DATABASE_URL`.
Opening a second, unrelated session inside `record_call` would either write
to the wrong database in dev/CI or fail outright, and every mock call
(success or failure, across every adapter) calls this on its way out, so
the whole suite would break, not just CQ-009's own tests. Every `Mock*`
class instead takes `session: AsyncSession` at construction (Protocols only
constrain the async business methods, not `__init__`) and passes it
through here, so the call log lands in the same session/transaction as
whatever the caller is already doing -- which is also what makes the
per-test transaction rollback in `backend/conftest.py`'s `db_session`
fixture actually roll these rows back too.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.models import IntegrationCall


async def record_call(
    session: AsyncSession,
    adapter: str,
    request_summary: dict[str, Any],
    success: bool,
    latency_ms: int,
    *,
    error_code: str | None = None,
    application_id: uuid.UUID | None = None,
) -> None:
    session.add(
        IntegrationCall(
            adapter=adapter,
            request_summary=request_summary,
            success=success,
            latency_ms=latency_ms,
            error_code=error_code,
            application_id=application_id,
            called_at=datetime.now(UTC),
        )
    )
    await session.commit()
