"""Concurrent edits (stage-6 review M1): two requests for one application
must not create duplicate open flags or race on the `orig:` provenance row.

These tests need real concurrency, so they cannot use the shared
rollback-only `db_session` (one connection). This module overrides
`db_session` with a committing session and `client` with a fresh session
per request, then deletes everything it created.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.core.valkey import get_valkey
from app.features.applications.models import Application
from app.features.applications.verification.models import FieldValue, Flag
from app.features.auth.models import User
from app.features.clients.models import Client as ClientModel
from app.integrations.common.models import IntegrationCall
from app.integrations.credit.models import ProviderCreditReport
from app.integrations.los.models import ProviderLosRecord
from conftest import StaffSession

MakeApp = Callable[..., Awaitable[Application]]


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session = AsyncSession(bind=test_engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def client(
    app: FastAPI, test_engine: AsyncEngine, valkey: Redis
) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def _override_get_valkey() -> AsyncIterator[Redis]:
        yield valkey

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_valkey] = _override_get_valkey
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_valkey, None)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(test_engine: AsyncEngine, staff: StaffSession) -> AsyncIterator[None]:
    yield
    async with test_engine.begin() as conn:
        apps = (
            await conn.execute(
                select(Application.id, Application.los_loan_guid).where(
                    Application.lo_id == staff.user.id
                )
            )
        ).all()
        ids = [row.id for row in apps]
        loans = [row.los_loan_guid for row in apps if row.los_loan_guid]
        await conn.execute(delete(IntegrationCall).where(IntegrationCall.application_id.in_(ids)))
        await conn.execute(delete(Application).where(Application.id.in_(ids)))
        await conn.execute(
            delete(ProviderLosRecord).where(ProviderLosRecord.loan_number.in_(loans))
        )
        await conn.execute(
            delete(ProviderCreditReport).where(ProviderCreditReport.loan_number.in_(loans))
        )
        await conn.execute(delete(ClientModel).where(ClientModel.assigned_lo_id == staff.user.id))
        await conn.execute(delete(User).where(User.id == staff.user.id))


async def _open_flags(db: AsyncSession, application_id: uuid.UUID, rule: str) -> int:
    return (
        await db.execute(
            select(func.count(Flag.id)).where(
                Flag.application_id == application_id,
                Flag.rule == rule,
                Flag.resolved_at.is_(None),
            )
        )
    ).scalar_one()


async def test_concurrent_edits_leave_one_open_flag(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app(ssn="123456789")
    url = f"/api/v1/applications/{app.id}/fields/borrower_ssn"
    # The first edit writes the `orig:` row, so the race below is only on flags.
    assert (await client.put(url, json={"value": "111223333"})).status_code == 200

    for attempt in range(5):
        responses = await asyncio.gather(
            client.put(url, json={"value": f"12{attempt}"}),
            client.put(url, json={"value": f"34{attempt}5"}),
        )
        assert [r.status_code for r in responses] == [200, 200]
        assert await _open_flags(db_session, app.id, "ssn_format") == 1
        # Clear it again so the next round raises a fresh flag concurrently.
        assert (await client.put(url, json={"value": "111223333"})).status_code == 200
        assert await _open_flags(db_session, app.id, "ssn_format") == 0


async def test_concurrent_first_edits_write_one_orig_row(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    for _ in range(3):
        app = await make_app()
        url = f"/api/v1/applications/{app.id}/fields/borrower_work_phone"

        responses = await asyncio.gather(
            client.put(url, json={"value": "2605550001"}),
            client.put(url, json={"value": "2605550002"}),
        )

        assert [r.status_code for r in responses] == [200, 200]
        rows = (
            (
                await db_session.execute(
                    select(FieldValue).where(
                        FieldValue.application_id == app.id,
                        FieldValue.field_key == "orig:borrower_work_phone",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].value is None  # the imported (empty) original is kept
