"""CQ-030 spec.md AC1-AC5: `mark_stale` / `clear_stale` on real seeded
personas (the same seed loader `make demo-reset` runs)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from seed.loader import (
    apply_send_fixture,
    load_persona_fixtures,
    seed_persona,
    seed_providers,
    seed_users,
)
from seed.pricing_seam import run_pricing_stage
from sqlalchemy import event as sa_event
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.clients.models import Client
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from app.features.quotes.stale.schemas import StaleResult
from app.features.quotes.stale.service import (
    EVENT_APPLICATION_STALE,
    EVENT_REPRICED_FROM_STALE,
    clear_stale,
    mark_application_quotes_stale,
    mark_stale,
)


async def _seed(db: AsyncSession, *keys: str) -> dict[str, Application]:
    users = await seed_users(db)
    await seed_providers(db)
    personas = {p["key"]: p for p in load_persona_fixtures()}
    seeded: dict[str, Application] = {}
    for key in keys:
        result = await seed_persona(db, personas[key], lo_id=users.lo_ids[0], s3_client=None)
        application = await db.get(Application, result.application_id)
        assert application is not None
        seeded[key] = application
    return seeded


async def _quotes(db: AsyncSession, application_id: uuid.UUID) -> list[Quote]:
    rows = await db.execute(
        select(Quote)
        .join(Scenario, Quote.scenario_id == Scenario.id)
        .where(Scenario.application_id == application_id)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _stale_events(db: AsyncSession, application_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(ActivityEvent)
            .where(
                ActivityEvent.application_id == application_id,
                ActivityEvent.type == EVENT_APPLICATION_STALE,
            )
        )
    ).scalar_one()


async def _status(db: AsyncSession, application: Application) -> ApplicationStatus:
    await db.refresh(application)
    return application.status


async def test_mark_stale_grace_kim(db_session: AsyncSession) -> None:
    """AC1: after the seed (sent 25 days ago), one run marks Grace's quotes
    stale and her status Stale, and writes exactly one activity event."""
    grace = (await _seed(db_session, "grace_kim"))["grace_kim"]
    assert grace.status is ApplicationStatus.SENT

    result = await mark_stale(db_session, datetime.now(UTC))

    assert await _status(db_session, grace) is ApplicationStatus.STALE
    quotes = await _quotes(db_session, grace.id)
    assert quotes and all(q.stale for q in quotes)
    assert await _stale_events(db_session, grace.id) == 1
    event = (
        await db_session.execute(
            select(ActivityEvent).where(
                ActivityEvent.application_id == grace.id,
                ActivityEvent.type == EVENT_APPLICATION_STALE,
            )
        )
    ).scalar_one()
    assert isinstance(event.payload, dict)
    assert event.payload["message"] == "Quotes older than 21 days"
    assert event.actor == "system"
    assert result.applications_marked_stale == 1
    assert result.application_ids == [str(grace.id)]
    assert result.versions_expired == 1
    assert result.quotes_marked_stale == len(quotes)


async def test_mark_stale_idempotent(db_session: AsyncSession) -> None:
    """AC2: a second run changes nothing and writes no events."""
    grace = (await _seed(db_session, "grace_kim"))["grace_kim"]
    now = datetime.now(UTC)
    await mark_stale(db_session, now)
    events_before = await _stale_events(db_session, grace.id)

    second = await mark_stale(db_session, now)

    assert second == StaleResult()
    assert await _stale_events(db_session, grace.id) == events_before == 1
    assert await _status(db_session, grace) is ApplicationStatus.STALE


async def test_mark_stale_clock_boundaries(
    db_session: AsyncSession,
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: Marcus Hale sent at T. At T+20d nothing changes; at T+22d he is
    Stale, the version is expired, and his report shows `expired`."""
    marcus = (await _seed(db_session, "marcus_hale"))["marcus_hale"]
    assert await _quotes(db_session, marcus.id)
    await apply_send_fixture(
        db_session,
        application_id=marcus.id,
        sent_days_ago=0,
        viewed_days_ago=None,
        borrower_action=None,
        borrower_email="marcus.hale@clearquote-demo.test",
    )
    version = (
        await db_session.execute(
            select(QuotePackageVersion)
            .join(QuotePackage, QuotePackageVersion.package_id == QuotePackage.id)
            .where(QuotePackage.application_id == marcus.id)
        )
    ).scalar_one()
    sent_at = version.sent_at
    assert await _status(db_session, marcus) is ApplicationStatus.SENT

    at_20 = await mark_stale(db_session, sent_at + timedelta(days=20))
    assert at_20 == StaleResult()
    assert await _status(db_session, marcus) is ApplicationStatus.SENT
    assert await _stale_events(db_session, marcus.id) == 0

    at_22_now = sent_at + timedelta(days=22)
    at_22 = await mark_stale(db_session, at_22_now)
    assert await _status(db_session, marcus) is ApplicationStatus.STALE
    assert await _stale_events(db_session, marcus.id) == 1
    assert at_22.versions_expired == 1
    await db_session.refresh(version)
    assert version.expired_at == at_22_now
    assert all(q.stale for q in await _quotes(db_session, marcus.id))

    # His report (CQ-022) shows expired with CLOCK_NOW at T+22d.
    frozen = get_settings().model_copy(update={"clock_now": at_22_now.isoformat()})
    monkeypatch.setattr(clock, "get_settings", lambda: frozen)
    client_row = await db_session.get(Client, marcus.client_id)
    assert client_row is not None
    await make_borrower_session(client_row)
    response = await client.get(f"/api/v1/portal/reports/{version.report_token}")
    assert response.status_code == 200, response.text
    assert response.json()["header"]["expired"] is True


async def test_option_selected_keeps_status(db_session: AsyncSession) -> None:
    """AC4: Luis Romero (OptionSelected) keeps his status; his quotes are
    flagged stale; no status event is written."""
    luis = (await _seed(db_session, "luis_romero"))["luis_romero"]
    assert luis.status is ApplicationStatus.OPTION_SELECTED

    result = await mark_stale(db_session, datetime.now(UTC) + timedelta(days=22))

    assert await _status(db_session, luis) is ApplicationStatus.OPTION_SELECTED
    quotes = await _quotes(db_session, luis.id)
    assert quotes and all(q.stale for q in quotes)
    assert await _stale_events(db_session, luis.id) == 0
    assert result.applications_marked_stale == 0


async def test_reprice_clears_stale(db_session: AsyncSession) -> None:
    """AC5 (pending -- re-check after CQ-018): re-pricing Grace through the
    pipeline's pricing stage, then `clear_stale` (the hook CQ-018's
    `/reprice` calls), moves her to Priced with fresh `priced_at` and
    clears the stale flags; the next run changes nothing."""
    grace = (await _seed(db_session, "grace_kim"))["grace_kim"]
    await mark_stale(db_session, datetime.now(UTC))
    assert await _status(db_session, grace) is ApplicationStatus.STALE

    old_ids = {q.id for q in await _quotes(db_session, grace.id)}
    before_reprice = datetime.now(UTC)
    stage = await run_pricing_stage(db_session, grace.id)
    new_ids = set(stage.quote_set_result.quote_ids)
    moved = await clear_stale(db_session, grace.id, fresh_quote_ids=list(new_ids))

    assert moved is True
    assert await _status(db_session, grace) is ApplicationStatus.PRICED
    quotes = await _quotes(db_session, grace.id)
    fresh = [q for q in quotes if q.id in new_ids]
    assert fresh and all(q.priced_at >= before_reprice for q in fresh)
    assert not any(q.stale for q in fresh)
    # Superseded quotes the re-price did not write keep their flag (m3).
    assert all(q.stale for q in quotes if q.id in old_ids - new_ids)

    assert await mark_stale(db_session, datetime.now(UTC)) == StaleResult()
    assert await _status(db_session, grace) is ApplicationStatus.PRICED


async def test_clear_stale_uses_fresh_ids_not_a_time_window(db_session: AsyncSession) -> None:
    """Review M1: under a frozen `CLOCK_NOW` far ahead of the real clock,
    `clear_stale` still clears exactly the ids it is given and moves the
    application Stale -> Priced; quotes it is not given keep their flag
    even when they are recent (m3)."""
    marcus = (await _seed(db_session, "marcus_hale"))["marcus_hale"]
    quotes = await _quotes(db_session, marcus.id)
    assert len(quotes) >= 2
    future = datetime.now(UTC) + timedelta(days=60)
    await mark_stale(db_session, future)
    assert await _status(db_session, marcus) is ApplicationStatus.STALE

    fresh_id = quotes[0].id
    moved = await clear_stale(db_session, marcus.id, fresh_quote_ids=[fresh_id], now=future)

    assert moved is True
    assert await _status(db_session, marcus) is ApplicationStatus.PRICED
    by_id = {q.id: q for q in await _quotes(db_session, marcus.id)}
    assert by_id[fresh_id].stale is False
    assert all(q.stale for qid, q in by_id.items() if qid != fresh_id)
    event = (
        await db_session.execute(
            select(ActivityEvent).where(
                ActivityEvent.application_id == marcus.id,
                ActivityEvent.type == EVENT_REPRICED_FROM_STALE,
            )
        )
    ).scalar_one()
    assert event.at == future


async def test_clear_stale_without_fresh_quotes_keeps_stale(db_session: AsyncSession) -> None:
    """No fresh quotes (or ids from another application) -> nothing is
    cleared and the status stays Stale."""
    seeded = await _seed(db_session, "marcus_hale", "grace_kim")
    marcus, grace = seeded["marcus_hale"], seeded["grace_kim"]
    await mark_stale(db_session, datetime.now(UTC) + timedelta(days=60))
    grace_quote_ids = [q.id for q in await _quotes(db_session, grace.id)]

    assert await clear_stale(db_session, marcus.id, fresh_quote_ids=[]) is False
    assert await clear_stale(db_session, marcus.id, fresh_quote_ids=grace_quote_ids) is False

    assert await _status(db_session, marcus) is ApplicationStatus.STALE
    assert all(q.stale for q in await _quotes(db_session, marcus.id))
    assert all(q.stale for q in await _quotes(db_session, grace.id))


async def test_mark_stale_strict_boundary_on_quote_age(db_session: AsyncSession) -> None:
    """Spec note: stale only when age is strictly greater than 21 days --
    exactly 21 days old is still fresh."""
    marcus = (await _seed(db_session, "marcus_hale"))["marcus_hale"]
    quotes = await _quotes(db_session, marcus.id)
    newest = max(q.priced_at for q in quotes)

    assert await mark_stale(db_session, newest + timedelta(days=21)) == StaleResult(
        quotes_marked_stale=sum(1 for q in quotes if q.priced_at < newest)
    )
    assert await _status(db_session, marcus) is ApplicationStatus.PRICED

    result = await mark_stale(db_session, newest + timedelta(days=21, microseconds=1))
    assert await _status(db_session, marcus) is ApplicationStatus.STALE
    assert result.applications_marked_stale == 1


async def test_mark_application_quotes_stale_helper(db_session: AsyncSession) -> None:
    """E12 shared helper: flags every quote once, returns the count, and
    never changes status or writes events."""
    marcus = (await _seed(db_session, "marcus_hale"))["marcus_hale"]
    count = len(await _quotes(db_session, marcus.id))

    assert await mark_application_quotes_stale(db_session, marcus.id, "fico_bucket") == count
    assert await mark_application_quotes_stale(db_session, marcus.id, "fico_bucket") == 0
    assert await _status(db_session, marcus) is ApplicationStatus.PRICED
    assert await _stale_events(db_session, marcus.id) == 0


async def test_first_report_view_does_not_overwrite_stale(
    db_session: AsyncSession,
    client: AsyncClient,
    make_borrower_session: Callable[..., Awaitable[object]],
) -> None:
    """Review finding: the report's Sent -> Viewed write is conditional, so
    it never overwrites a Stale status the job already committed."""
    grace = (await _seed(db_session, "grace_kim"))["grace_kim"]
    await mark_stale(db_session, datetime.now(UTC))
    version = (
        await db_session.execute(
            select(QuotePackageVersion)
            .join(QuotePackage, QuotePackageVersion.package_id == QuotePackage.id)
            .where(QuotePackage.application_id == grace.id)
        )
    ).scalar_one()
    client_row = await db_session.get(Client, grace.client_id)
    await make_borrower_session(client_row)

    response = await client.get(f"/api/v1/portal/reports/{version.report_token}")

    assert response.status_code == 200, response.text
    assert response.json()["header"]["expired"] is True
    assert await _status(db_session, grace) is ApplicationStatus.STALE


async def test_newer_quotes_outrank_an_old_recommended_quote(db_session: AsyncSession) -> None:
    """Review finding: a re-price that writes new quotes without repointing
    `recommended_quote_id` must not flip the application back to Stale --
    the newest `priced_at` decides."""
    marcus = (await _seed(db_session, "marcus_hale"))["marcus_hale"]
    quotes = await _quotes(db_session, marcus.id)
    old = quotes[0]
    old.priced_at = old.priced_at - timedelta(days=30)
    marcus.recommended_quote_id = old.id
    await db_session.flush()

    result = await mark_stale(db_session, datetime.now(UTC))

    assert await _status(db_session, marcus) is ApplicationStatus.PRICED
    assert result.applications_marked_stale == 0
    assert result.quotes_marked_stale == 1


async def _send_marcus(db: AsyncSession, marcus: Application, quote_ids: list[uuid.UUID]) -> None:
    await apply_send_fixture(
        db,
        application_id=marcus.id,
        sent_days_ago=0,
        viewed_days_ago=None,
        borrower_action=None,
        borrower_email="marcus.hale@clearquote-demo.test",
    )


async def test_version_expired_flags_only_sent_or_old_quotes(db_session: AsyncSession) -> None:
    """Review m5: when an expired version (not quote age) moves the
    application to Stale, only the version's quotes and quotes older than
    the cutoff are flagged; a fresh quote outside the version is not."""
    marcus = (await _seed(db_session, "marcus_hale"))["marcus_hale"]
    quotes = await _quotes(db_session, marcus.id)
    assert len(quotes) >= 2
    sent_id = quotes[0].id
    await _send_marcus(db_session, marcus, [sent_id])
    # P56-merge: main's CQ-019 `apply_send_fixture` now picks the package's
    # quotes itself (`new_default_package`), so narrow the sent package and
    # its version to the one quote this test sends.
    await db_session.execute(
        update(QuotePackage)
        .where(QuotePackage.application_id == marcus.id)
        .values(quote_ids=[sent_id])
    )
    now = datetime.now(UTC)
    await db_session.execute(
        update(QuotePackageVersion)
        .where(
            QuotePackageVersion.package_id.in_(
                select(QuotePackage.id).where(QuotePackage.application_id == marcus.id)
            )
        )
        .values(
            expires_at=now - timedelta(minutes=1),
            snapshot={"options": [{"quote_id": str(sent_id)}]},
        )
    )

    result = await mark_stale(db_session, now)

    assert await _status(db_session, marcus) is ApplicationStatus.STALE
    by_id = {q.id: q for q in await _quotes(db_session, marcus.id)}
    assert by_id[sent_id].stale is True
    assert not any(q.stale for qid, q in by_id.items() if qid != sent_id)
    assert result.quotes_marked_stale == 1


async def test_candidates_are_locked_and_from_status_read_from_the_row(
    db_session: AsyncSession,
) -> None:
    """Review m2: candidate applications are read `FOR UPDATE`, and the
    event's `from_status` comes from the locked row, not a stale ORM copy."""
    marcus = (await _seed(db_session, "marcus_hale"))["marcus_hale"]
    quote_ids = [q.id for q in await _quotes(db_session, marcus.id)]
    await _send_marcus(db_session, marcus, quote_ids)
    assert marcus.status is ApplicationStatus.SENT
    # A concurrent Sent -> Viewed that this session's identity map missed.
    await db_session.execute(
        update(Application)
        .where(Application.id == marcus.id)
        .values(status=ApplicationStatus.VIEWED)
        .execution_options(synchronize_session=False)
    )
    assert marcus.status is ApplicationStatus.SENT

    statements: list[str] = []

    def _record(conn: object, cursor: object, statement: str, *args: object) -> None:
        statements.append(statement)

    sync_conn = (await db_session.connection()).sync_connection
    assert sync_conn is not None
    sa_event.listen(sync_conn, "before_cursor_execute", _record)
    try:
        await mark_stale(db_session, datetime.now(UTC) + timedelta(days=22))
    finally:
        sa_event.remove(sync_conn, "before_cursor_execute", _record)

    app_locks = [
        i
        for i, s in enumerate(statements)
        if s.lstrip().startswith("SELECT applications.") and "FOR UPDATE" in s
    ]
    quote_locks = [i for i, s in enumerate(statements) if "FOR UPDATE OF quotes" in s]
    assert app_locks, statements
    # Review follow-up: candidates' quotes are locked before the
    # applications, so step 3's quote updates keep quotes -> applications.
    assert quote_locks and quote_locks[0] < app_locks[0], statements
    event = (
        await db_session.execute(
            select(ActivityEvent).where(
                ActivityEvent.application_id == marcus.id,
                ActivityEvent.type == EVENT_APPLICATION_STALE,
            )
        )
    ).scalar_one()
    assert isinstance(event.payload, dict)
    assert event.payload["from_status"] == "viewed"
