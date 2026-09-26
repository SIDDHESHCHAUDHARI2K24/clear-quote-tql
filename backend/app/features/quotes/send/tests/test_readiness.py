"""CQ-019 AC5: send readiness blockers."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.clients.models import Client
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _seed
from app.features.quotes.stale.service import STALE_QUOTE_DAYS_KEY
from app.features.settings.models import Setting
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]


async def _readiness(client: AsyncClient, application_id: uuid.UUID) -> dict[str, Any]:
    package = (await client.get(f"/api/v1/applications/{application_id}/package")).json()
    response = await client.get(f"/api/v1/packages/{package['id']}/readiness")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("persona", ["grace_kim", "aisha_coleman"])
async def test_readiness_blockers(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff, persona: str
) -> None:
    ids = await _seed(db_session, persona)
    await make_staff_session(role=UserRole.MANAGER)
    readiness = await _readiness(client, ids[persona])

    assert readiness["ready"] is False
    first = readiness["blockers"][0]
    if persona == "grace_kim":
        # Sent 25 days ago: its quotes are past the 21-day rate window.
        assert first == {
            "code": "quotes_stale",
            "message": "Quotes are out of date",
            "tab": "pricing",
        }
    else:
        # Aisha Coleman: missing Occupancy is an open blocking flag.
        assert first["code"] == "open_flag"
        assert first["message"] == "Open flag: Occupancy type — required for pricing"
        assert first["tab"] == "pricing"


async def test_ready_package_has_no_blockers(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    assert await _readiness(client, ids["marcus_hale"]) == {"ready": True, "blockers": []}


async def test_readiness_stale_flag_missing_recommendation_and_email(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)
    package = (await client.get(f"/api/v1/applications/{application_id}/package")).json()

    await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={"quote_ids": package["quote_ids"], "recommended_quote_id": None},
    )
    await db_session.execute(
        # A UUID, not the JSON string: the session syncs its cached Quote by
        # evaluating this criterion in Python, where UUID != str -- the
        # cached copy then stayed un-stale whenever it was still alive.
        update(Quote).where(Quote.id == uuid.UUID(package["quote_ids"][1])).values(stale=True)
    )
    application = await db_session.get(Application, application_id)
    assert application is not None
    await db_session.execute(
        update(Client).where(Client.id == application.client_id).values(email="")
    )
    await db_session.commit()

    codes = [b["code"] for b in (await _readiness(client, application_id))["blockers"]]
    assert codes == ["quotes_stale", "no_recommended_quote", "borrower_email_missing"]


async def test_manual_quote_no_longer_offered_blocks(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """CQ-018 follow-up: a Manual quote left stale by a reprice (its product
    left the grid) is named in readiness."""
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)
    package = (await client.get(f"/api/v1/applications/{application_id}/package")).json()
    par = await db_session.get(Quote, uuid.UUID(package["quote_ids"][0]))
    assert par is not None
    manual = Quote(
        scenario_id=par.scenario_id,
        investor=par.investor,
        product="Retired Product",
        rate=par.rate,
        points=par.points,
        lock_days=par.lock_days,
        computed=par.computed,
        label="Manual",
        priced_at=par.priced_at - timedelta(hours=1),
        stale=True,
    )
    db_session.add(manual)
    await db_session.commit()
    response = await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={"quote_ids": [str(par.id), str(manual.id)], "recommended_quote_id": str(par.id)},
    )
    assert response.status_code == 200, response.text

    blockers = (await _readiness(client, application_id))["blockers"]
    assert blockers[0]["code"] == "quotes_stale"
    assert blockers[1] == {
        "code": "quote_not_offered",
        "message": "1 manual quote is no longer offered — delete or re-pick",
        "tab": "pricing",
    }


async def test_readiness_blocks_instead_of_500_when_investment_strategy_is_missing(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M6: an investment application with no LTR/STR strategy set makes
    `strategy_type` raise inside `load_package_context`; unhandled that
    422s the whole readiness call and the Send tab is stuck on "Checking
    readiness…". It must come back as a blocker instead."""
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)
    application = await db_session.get(Application, application_id)
    assert application is not None
    assert application.occupancy is not None
    assert application.occupancy.value == "investment"
    # The default draft is created first, while the strategy is still set
    # (a fresh application with no draft yet and no strategy is a
    # different, unrelated gap in `new_default_package`'s own recommendation
    # drafting -- out of scope for this finding, which is about the
    # readiness call over an *existing* package).
    await client.get(f"/api/v1/applications/{application_id}/package")
    await db_session.execute(
        update(Application).where(Application.id == application_id).values(strategy=None)
    )
    await db_session.commit()

    readiness = await _readiness(client, application_id)
    assert readiness == {
        "ready": False,
        "blockers": [
            {
                "code": "strategy_missing",
                "message": "Pick a rental strategy (LTR or STR)",
                "tab": "property",
            }
        ],
    }


# --- U3 (merge plan M4/M5): the stale_quote_days setting and core/clock -------


def _freeze(monkeypatch: pytest.MonkeyPatch, at: datetime) -> None:
    frozen = get_settings().model_copy(update={"clock_now": at.isoformat()})
    monkeypatch.setattr(clock, "get_settings", lambda: frozen)


async def _set_stale_days(db: AsyncSession, days: int) -> None:
    await db.merge(Setting(key=STALE_QUOTE_DAYS_KEY, value=days))
    await db.commit()


async def test_readiness_reads_the_clock_and_the_setting(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U3: `is_rate_stale` uses `core/clock.now()` (CLOCK_NOW) and the
    `stale_quote_days` setting CQ-030's job reads -- not a second,
    hard-coded 21-day rule on the real clock."""
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)
    assert await _readiness(client, application_id) == {"ready": True, "blockers": []}
    newest = (
        await db_session.execute(
            select(func.max(Quote.priced_at))
            .join(Scenario, Quote.scenario_id == Scenario.id)
            .where(Scenario.application_id == application_id)
        )
    ).scalar_one()
    stale_first = {"code": "quotes_stale", "message": "Quotes are out of date", "tab": "pricing"}

    await _set_stale_days(db_session, 21)
    _freeze(monkeypatch, newest + timedelta(days=20))
    assert (await _readiness(client, application_id))["ready"] is True
    _freeze(monkeypatch, newest + timedelta(days=22))
    assert (await _readiness(client, application_id))["blockers"][0] == stale_first

    # The setting, not a constant: 30 days clears it at +22d, 10 flags +15d.
    await _set_stale_days(db_session, 30)
    assert (await _readiness(client, application_id))["ready"] is True
    await _set_stale_days(db_session, 10)
    _freeze(monkeypatch, newest + timedelta(days=15))
    assert (await _readiness(client, application_id))["blockers"][0] == stale_first
