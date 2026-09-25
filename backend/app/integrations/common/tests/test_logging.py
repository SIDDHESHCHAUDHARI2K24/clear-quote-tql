"""AC5: every mock call (success or failure) writes exactly one
`integration_calls` row with a correct `latency_ms` and `success` flag.

Also covers the review finding on `record_call` (post-dev.md #1): the audit
row must be written in its own short-lived session/transaction, independent
of whatever session the caller (a `Mock*` instance) is using.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.integrations.common.errors import LoanNotFoundError
from app.integrations.common.models import IntegrationCall
from app.integrations.los.mock import MockLosClient
from app.integrations.los.models import ProviderLosRecord


async def _los_call_rows(session: AsyncSession) -> list[IntegrationCall]:
    return list(
        (await session.execute(select(IntegrationCall).where(IntegrationCall.adapter == "los")))
        .scalars()
        .all()
    )


async def test_success_writes_one_row_with_latency_and_success(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderLosRecord(loan_number="LN-LOG-1", payload={"occupancy_type": "Primary_Residence"})
    )
    await db_session.commit()

    await MockLosClient(db_session).get_loan_file("LN-LOG-1")

    rows = await _los_call_rows(db_session)
    assert len(rows) == 1
    assert rows[0].success is True
    assert rows[0].error_code is None
    assert rows[0].latency_ms == 0  # latency disabled for the whole test session
    assert rows[0].request_summary == {"loan_number": "LN-LOG-1"}


async def test_failure_writes_one_row_with_error_code(db_session: AsyncSession) -> None:
    with pytest.raises(LoanNotFoundError):
        await MockLosClient(db_session).get_loan_file("MISSING-LOAN")

    rows = await _los_call_rows(db_session)
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].error_code == "LOAN_NOT_FOUND"
    assert rows[0].latency_ms == 0


async def test_audit_row_survives_caller_rollback(test_engine: AsyncEngine) -> None:
    """Reproduces `backend/conftest.py`'s `db_session` fixture logic
    standalone (like `backend/tests/test_db_isolation.py` does) so this test
    can roll the "caller" transaction back itself and then check, from a
    completely fresh connection, that the audit row is still there."""
    async with test_engine.connect() as conn:
        outer_transaction = await conn.begin()
        caller_session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            with pytest.raises(LoanNotFoundError):
                await MockLosClient(caller_session).get_loan_file("ROLLBACK-SURVIVOR")
        finally:
            await caller_session.close()
            await outer_transaction.rollback()

    async with test_engine.connect() as verify_conn:
        result = await verify_conn.execute(
            select(IntegrationCall).where(
                IntegrationCall.adapter == "los",
                IntegrationCall.error_code == "LOAN_NOT_FOUND",
            )
        )
        rows = result.fetchall()

    assert len(rows) == 1


async def test_provider_call_never_commits_the_callers_session(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller's pending work must stay pending -- `record_call` writing the
    audit row must not be the thing that commits it. Spied directly on the
    session object passed in, since that's the only session a `Mock*` ever
    touches."""
    commit_calls = 0
    original_commit = db_session.commit

    async def _tracking_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        await original_commit()

    monkeypatch.setattr(db_session, "commit", _tracking_commit)

    with pytest.raises(LoanNotFoundError):
        await MockLosClient(db_session).get_loan_file("NEVER-COMMIT-CALLER")

    assert commit_calls == 0
