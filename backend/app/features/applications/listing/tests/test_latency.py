"""spec.md AC5: "responds in under 300 ms for any filter combination on
the seed" -- built against a same-order-of-magnitude fixture set (a few
hundred applications, no pipeline) rather than the real seed, so this test
doesn't depend on `make demo-reset` having run."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Strategy, UserRole
from app.features.applications.listing.tests.conftest import (
    MakeApplication,
    MakeLo,
    add_specific_property,
    add_tbd_property,
)

_STATES = ["FL", "OH", "CO", "TX", "AZ"]
_STATUSES = [
    ApplicationStatus.INTAKE,
    ApplicationStatus.VERIFYING,
    ApplicationStatus.NEEDS_ATTENTION,
    ApplicationStatus.READY_TO_PRICE,
    ApplicationStatus.PRICED,
    ApplicationStatus.SENT,
    ApplicationStatus.STALE,
]
_STRATEGIES: list[Strategy | None] = [None, Strategy.LTR, Strategy.STR]


async def test_application_list_latency(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_application: MakeApplication,
) -> None:
    lo = await make_lo("Latency LO", UserRole.LO)
    for i in range(250):
        fixture = await make_application(
            lo=lo,
            client_name=f"Client {i}",
            client_email=f"client{i}@example.test",
            status=_STATUSES[i % len(_STATUSES)],
            strategy=_STRATEGIES[i % len(_STRATEGIES)],
            requested_price=Decimal(200_000 + (i * 1_000)),
        )
        if i % 3 == 0:
            await add_specific_property(
                db_session, fixture.application, state=_STATES[i % len(_STATES)]
            )
        elif i % 3 == 1:
            await add_tbd_property(
                db_session, fixture.application, buy_box_states=[_STATES[i % len(_STATES)]]
            )
    await db_session.flush()

    await make_staff_session(UserRole.MANAGER)

    combos = [
        {},
        {"status": "Priced,Inquiry,OptionSelected"},
        {"strategy": "ltr", "state": "FL"},
        {"amount_min": "220000", "amount_max": "300000"},
        {"has_property": "true", "sort": "amount"},
        {"q": "Client 1"},
    ]
    for params in combos:
        start = time.perf_counter()
        resp = await client.get("/api/v1/applications", params={**params, "page_size": 50})
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200, resp.text
        assert elapsed_ms < 300, f"{params} took {elapsed_ms:.1f} ms"
