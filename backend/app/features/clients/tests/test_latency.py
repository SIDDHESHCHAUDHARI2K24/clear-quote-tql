"""spec.md AC5: "the list and detail endpoints each respond in under 300 ms
on the seeded data" -- built against a same-order-of-magnitude fixture set
(mirrors `applications/listing/tests/test_latency.py`)."""

from __future__ import annotations

import time
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.clients.tests.conftest import (
    MakeApplicationFor,
    MakeClient,
    MakeLo,
    add_activity_event,
    add_sent_version,
)

_STATUSES = [
    ApplicationStatus.INTAKE,
    ApplicationStatus.VERIFYING,
    ApplicationStatus.NEEDS_ATTENTION,
    ApplicationStatus.PRICED,
    ApplicationStatus.SENT,
    ApplicationStatus.WITHDRAWN,
]


async def test_clients_list_latency(
    db_session: AsyncSession,
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    lo = await make_lo("Latency LO", UserRole.LO)
    for i in range(250):
        fixture = await make_client(lo=lo, full_name=f"Client {i}", email=f"client{i}@example.test")
        application = await make_application_for(
            fixture.client, lo, status=_STATUSES[i % len(_STATUSES)]
        )
        if i % 4 == 0:
            await add_activity_event(db_session, application)
    await db_session.flush()

    await make_staff_session(UserRole.MANAGER)

    combos = [
        {},
        {"has_active": "true"},
        {"sort": "-last_activity"},
        {"q": "Client 1"},
    ]
    for params in combos:
        start = time.perf_counter()
        resp = await client.get("/api/v1/clients", params={**params, "page_size": 50})
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200, resp.text
        assert elapsed_ms < 300, f"{params} took {elapsed_ms:.1f} ms"


async def test_client_detail_latency(
    db_session: AsyncSession,
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    lo = await make_lo("Detail Latency LO", UserRole.LO)
    fixture = await make_client(lo=lo, full_name="Busy Client", email="busy@example.test")
    for i in range(15):
        application = await make_application_for(
            fixture.client, lo, status=_STATUSES[i % len(_STATUSES)]
        )
        for j in range(10):
            await add_activity_event(db_session, application, type=f"pipeline.step_{j}")
        await add_sent_version(db_session, application, version=1)
    await db_session.flush()

    await make_staff_session(UserRole.MANAGER)

    start = time.perf_counter()
    resp = await client.get(f"/api/v1/clients/{fixture.client.id}")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200, resp.text
    assert elapsed_ms < 300, f"detail took {elapsed_ms:.1f} ms"
