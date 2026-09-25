"""Writes one `integration_calls` row per mock call, success or failure.

**Decision** (plan.md #2, revised after review -- post-dev.md finding #1):
`record_call` takes a leading `session: AsyncSession` argument (still a
deviation from spec.md's shorthand signature table, for the same original
reason: CQ-004's `app.core.db` module-level `engine`/`AsyncSessionLocal` is
permanently bound to `Settings.database_url`, a database CI's Postgres
service never creates, so the mocks can't use it and every `Mock*` instead
takes `session: AsyncSession` at construction). But `record_call` no longer
reuses that session to write the audit row. Two problems with the original
"just `session.add(...); await session.commit()` on the caller's session"
approach: (1) it commits *whatever else* the caller had pending, which an
audit log write must never do; (2) on the failure path -- exactly when
CQ-029's Integration panel most wants to show the row -- the caller's own
transaction is often about to roll back, which would take the audit row
down with it.

`record_call` instead opens its own short-lived `AsyncSession`, bound to
the same underlying `AsyncEngine` the caller's session is using (derived
from `session.bind`, not a second hardcoded engine), inserts, and commits
independently. That keeps `integration_calls` durable regardless of what
the caller does next, while still targeting whichever database the caller
is actually using (`TEST_DATABASE_URL` in tests, `DATABASE_URL` in prod).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.integrations.common.models import IntegrationCall


def _engine_for_session(session: AsyncSession) -> AsyncEngine:
    """Resolves the real `AsyncEngine` backing `session`, whether it was
    constructed directly from one (production's `AsyncSessionLocal`) or from
    a checked-out `AsyncConnection` (`backend/conftest.py`'s `db_session`
    fixture binds sessions to one connection so a whole test's writes share
    one outer transaction to roll back)."""
    bind = session.bind
    if isinstance(bind, AsyncEngine):
        return bind
    if isinstance(bind, AsyncConnection):
        return bind.engine
    raise RuntimeError(f"Cannot derive an AsyncEngine from session bind {bind!r}")


async def record_call(
    session: AsyncSession,
    adapter: str,
    request_summary: dict[str, Any],
    success: bool,
    latency_ms: int,
    *,
    error_code: str | None = None,
    application_id: uuid.UUID | None = None,
    audit_sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """`audit_sessionmaker` is an injectable override (tests or a future
    caller that wants to pin a specific engine); the default derives one
    from `session`'s own engine on every call, which is cheap (an
    `async_sessionmaker` just holds a factory, it doesn't open a connection
    until a session from it is actually used)."""
    maker = audit_sessionmaker or async_sessionmaker(
        _engine_for_session(session), expire_on_commit=False
    )
    async with maker() as audit_session:
        audit_session.add(
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
        await audit_session.commit()
