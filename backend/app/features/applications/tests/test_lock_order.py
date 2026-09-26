"""P5/P6 lock unification (merge plan decision M3, unit U2).

One lock order for the whole codebase -- quotes -> packages/versions ->
applications (`applications/locking.py`) -- so the P3 Quote Builder/Send
writers and the P5/P6 CQ-030 stale job / CQ-033 hard pull can never wait on
each other in a cycle.

Each race runs on two real connections against committed data (the usual
rollback-only `db_session` can't be seen from a second connection), with
one side paused while it holds its locks so the interleaving that used to
deadlock happens every run, not by chance. `_committed_data` empties the
tables the test filled afterwards.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.enums import ApplicationStatus, FieldSource
from app.features.applications.locking import (
    lock_application,
    lock_application_packages,
    lock_application_quotes,
)
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import BorrowerAccount, User
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.clients.models import Client as ClientModel
from app.features.notifications.email import service as email_service
from app.features.portal.consents import service as consents_service
from app.features.portal.consents.consent_text import HARD_PULL_TEXT_V1, HARD_PULL_TEXT_VERSION
from app.features.pricing.enrichment import router as enrichment_router
from app.features.pricing.enrichment.schemas import FieldValueOverrideRequest
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder import service as builder_service
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _seed
from app.features.quotes.delivery import steps
from app.features.quotes.delivery.tests.test_send_review_fixes import _committed_data
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from app.features.quotes.send.service import get_or_create_package
from app.features.quotes.stale import service as stale_service
from app.integrations.credit.models import CreditPullType, ProviderCreditReport

RACE_TIMEOUT = 30
PAUSE = 0.6
FIELD = "property_tax_annual_rate"

Factory = async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def factory(test_engine: AsyncEngine) -> AsyncIterator[Factory]:
    async with _committed_data(test_engine):
        yield async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _no_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_send(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(email_service, "smtp_send", _fake_send)


async def _seed_marcus(factory: Factory) -> uuid.UUID:
    async with factory() as db:
        ids = await _seed(db, "marcus_hale")
        await db.commit()
    return ids["marcus_hale"]


async def _quotes(db: AsyncSession, application_id: uuid.UUID) -> list[Quote]:
    return list(
        (
            await db.execute(
                select(Quote)
                .join(Scenario, Scenario.id == Quote.scenario_id)
                .where(Scenario.application_id == application_id)
                .order_by(Quote.id)
            )
        )
        .scalars()
        .all()
    )


async def _events(db: AsyncSession, application_id: uuid.UUID, type_: str) -> int:
    return (
        await db.execute(
            select(func.count(ActivityEvent.id)).where(
                ActivityEvent.application_id == application_id, ActivityEvent.type == type_
            )
        )
    ).scalar_one()


def _paused(
    original: Callable[..., Awaitable[Any]], holding: asyncio.Event, *, before: bool = True
) -> Callable[..., Awaitable[Any]]:
    """Wraps a step that runs while its caller holds its locks: signals
    `holding`, then keeps the locks for `PAUSE` seconds."""

    async def _wrapper(*args: Any, **kwargs: Any) -> Any:
        if before:
            holding.set()
            await asyncio.sleep(PAUSE)
            return await original(*args, **kwargs)
        result = await original(*args, **kwargs)
        holding.set()
        await asyncio.sleep(PAUSE)
        return result

    return _wrapper


# --- reprice vs CQ-030 mark_stale ---------------------------------------------


async def _reprice(factory: Factory, application_id: uuid.UUID) -> None:
    async with factory() as db:
        application = await db.get(Application, application_id)
        assert application is not None
        user = await db.get(User, application.lo_id)
        assert user is not None
        await builder_service.reprice_application(db, application, user)


async def _mark_stale(factory: Factory, at: Any) -> None:
    async with factory() as db:
        await stale_service.mark_stale(db, at)
        await db.commit()


async def test_reprice_holding_its_locks_then_mark_stale_does_not_deadlock(
    factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reprice takes its locks, then `mark_stale` starts. Before M3 reprice
    held only the application while `mark_stale` locked the quotes and then
    waited for the application -- reprice's quote UPDATE closed the cycle.
    Now `mark_stale` waits at its first quote lock and runs after reprice,
    so its result (every quote stale, the application Stale) is the end
    state."""
    app_id = await _seed_marcus(factory)
    holding = asyncio.Event()
    monkeypatch.setattr(
        builder_service, "ensure_priceable", _paused(builder_service.ensure_priceable, holding)
    )
    later = now() + timedelta(days=60)

    async def _stale_after_reprice_locks() -> None:
        await holding.wait()
        await _mark_stale(factory, later)

    await asyncio.wait_for(
        asyncio.gather(_reprice(factory, app_id), _stale_after_reprice_locks()),
        timeout=RACE_TIMEOUT,
    )

    async with factory() as db:
        quotes = await _quotes(db, app_id)
        application = await db.get(Application, app_id)
        assert application is not None
        assert quotes and all(q.stale for q in quotes)
        assert application.status is ApplicationStatus.STALE
        assert await _events(db, app_id, "quotes.repriced") == 1
        assert await _events(db, app_id, stale_service.EVENT_APPLICATION_STALE) == 1


async def test_mark_stale_holding_its_locks_then_reprice_does_not_deadlock(
    factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other order: `mark_stale` holds its quote and application locks,
    reprice waits at its first (quote) lock and runs after, so its fresh
    quotes are the end state."""
    app_id = await _seed_marcus(factory)
    holding = asyncio.Event()
    monkeypatch.setattr(
        stale_service,
        "_deciding_quote_priced_at",
        _paused(stale_service._deciding_quote_priced_at, holding),
    )
    later = now() + timedelta(days=60)

    async def _reprice_after_stale_locks() -> None:
        await holding.wait()
        await _reprice(factory, app_id)

    await asyncio.wait_for(
        asyncio.gather(_mark_stale(factory, later), _reprice_after_stale_locks()),
        timeout=RACE_TIMEOUT,
    )

    async with factory() as db:
        quotes = await _quotes(db, app_id)
        assert quotes and not any(q.stale for q in quotes)
        assert await _events(db, app_id, "quotes.repriced") == 1
        assert await _events(db, app_id, stale_service.EVENT_APPLICATION_STALE) == 1


async def test_mark_stale_locks_its_quotes_by_id_before_updating(
    factory: Factory, test_engine: AsyncEngine
) -> None:
    """Step 1 locks (ordered by id) before its UPDATE, so while another
    session holds one of the application's quotes, `mark_stale` updates
    nothing -- it waits at the lock instead of updating in heap order."""
    app_id = await _seed_marcus(factory)
    async with factory() as holder:
        await lock_application_quotes(holder, app_id)
        async with factory() as job:
            await job.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(Exception, match="lock timeout|LockNotAvailable"):
                await stale_service.mark_stale(job, now() + timedelta(days=60))
            await job.rollback()
        await holder.rollback()


# --- send (freeze / record) vs CQ-033 hard-pull accept ------------------------


WORKFLOW_ID = "u2-lock-order-send"


async def _prepare_send_and_consent(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Marcus with a ready package whose send is `WORKFLOW_ID`, a pending
    hard-pull consent and a borrower account. Returns (app, package,
    consent) ids."""
    app_id = await _seed_marcus(factory)
    async with factory() as db:
        application = await db.get(Application, app_id)
        assert application is not None and application.los_loan_guid is not None
        package = await get_or_create_package(db, application)
        package.send_workflow_id = WORKFLOW_ID
        report = (
            await db.execute(
                select(ProviderCreditReport).where(
                    ProviderCreditReport.loan_number == application.los_loan_guid,
                    ProviderCreditReport.pull_type == CreditPullType.HARD_PULL,
                )
            )
        ).scalar_one_or_none()
        if report is None:
            db.add(
                ProviderCreditReport(
                    loan_number=application.los_loan_guid,
                    pull_type=CreditPullType.HARD_PULL,
                    experian_score=640,
                    equifax_score=650,
                    transunion_score=660,
                    middle_score=650,
                    tradelines=[],
                )
            )
        consent = Consent(
            application_id=app_id,
            type=ConsentType.HARD_PULL,
            status=ConsentStatus.PENDING,
            requested_at=now(),
            expires_at=now() + timedelta(days=14),
        )
        db.add(consent)
        db.add(
            BorrowerAccount(
                client_id=application.client_id,
                email=f"u2-{uuid.uuid4().hex[:8]}@clearquote-demo.test",
            )
        )
        await db.commit()
        return app_id, package.id, consent.id


async def _accept(factory: Factory, app_id: uuid.UUID, consent_id: uuid.UUID) -> None:
    async with factory() as db:
        application = await db.get(Application, app_id)
        assert application is not None
        borrower = (
            await db.execute(
                select(BorrowerAccount).where(BorrowerAccount.client_id == application.client_id)
            )
        ).scalar_one()
        client_row = await db.get(ClientModel, application.client_id)
        assert client_row is not None
        out = await consents_service.accept_consent(
            db,
            borrower=borrower,
            consent_id=consent_id,
            typed_name=client_row.full_name,
            text_version=HARD_PULL_TEXT_VERSION,
            text_sha256=hashlib.sha256(HARD_PULL_TEXT_V1.encode()).hexdigest(),
            ip=None,
            user_agent=None,
        )
        assert out.status == "accepted"


async def _freeze_and_record(factory: Factory, package_id: uuid.UUID) -> None:
    async with factory() as db:
        version_id = await steps.freeze(db, package_id, WORKFLOW_ID)
    async with factory() as db:
        await steps.record(db, version_id, WORKFLOW_ID)


async def _assert_sent_and_pulled(
    factory: Factory, app_id: uuid.UUID, package_id: uuid.UUID
) -> None:
    async with factory() as db:
        application = await db.get(Application, app_id)
        assert application is not None
        assert application.status is ApplicationStatus.SENT
        versions = (
            await db.execute(
                select(func.count(QuotePackageVersion.id)).where(
                    QuotePackageVersion.package_id == package_id
                )
            )
        ).scalar_one()
        assert versions == 1
        assert await _events(db, app_id, steps.SENT_EVENT_TYPE) == 1
        assert await _events(db, app_id, "credit.hard_pull_completed") == 1


async def test_hard_pull_holding_its_locks_then_send_does_not_deadlock(
    factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_id, package_id, consent_id = await _prepare_send_and_consent(factory)
    holding = asyncio.Event()
    monkeypatch.setattr(
        consents_service,
        "perform_hard_pull",
        _paused(consents_service.perform_hard_pull, holding, before=False),
    )

    async def _send_after_pull_locks() -> None:
        await holding.wait()
        await _freeze_and_record(factory, package_id)

    await asyncio.wait_for(
        asyncio.gather(_accept(factory, app_id, consent_id), _send_after_pull_locks()),
        timeout=RACE_TIMEOUT,
    )
    await _assert_sent_and_pulled(factory, app_id, package_id)


async def test_send_record_holding_its_lock_then_hard_pull_does_not_deadlock(
    factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_id, package_id, consent_id = await _prepare_send_and_consent(factory)
    holding = asyncio.Event()
    monkeypatch.setattr(
        steps.MockCrmClient,
        "log_event",
        _paused(steps.MockCrmClient.log_event, holding),
    )

    async def _pull_after_record_lock() -> None:
        await holding.wait()
        await _accept(factory, app_id, consent_id)

    await asyncio.wait_for(
        asyncio.gather(_freeze_and_record(factory, package_id), _pull_after_record_lock()),
        timeout=RACE_TIMEOUT,
    )
    await _assert_sent_and_pulled(factory, app_id, package_id)


async def test_send_record_holding_its_locks_then_a_star_does_not_deadlock(
    factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding (U2 code review): `record` UPDATEs the package at its
    end, so it must lock the package before the application like the Quote
    Builder's star (packages -> application) -- otherwise a star during
    `record` deadlocks."""
    app_id, package_id, _consent_id = await _prepare_send_and_consent(factory)
    async with factory() as db:
        version_id = await steps.freeze(db, package_id, WORKFLOW_ID)
    async with factory() as db:
        stars_before = await _events(db, app_id, "quote.recommended")
    holding = asyncio.Event()
    monkeypatch.setattr(
        steps.MockCrmClient, "log_event", _paused(steps.MockCrmClient.log_event, holding)
    )

    async def _record() -> None:
        async with factory() as db:
            await steps.record(db, version_id, WORKFLOW_ID)

    async def _star_after_record_locks() -> None:
        await holding.wait()
        async with factory() as db:
            quote = (await _quotes(db, app_id))[-1]
            application = await db.get(Application, app_id)
            assert application is not None
            user = await db.get(User, application.lo_id)
            assert user is not None
            await builder_service.recommend_quote(db, quote, user)

    await asyncio.wait_for(
        asyncio.gather(_record(), _star_after_record_locks()), timeout=RACE_TIMEOUT
    )
    async with factory() as db:
        application = await db.get(Application, app_id)
        assert application is not None
        assert application.status is ApplicationStatus.SENT
        assert await _events(db, app_id, "quote.recommended") == stars_before + 1


async def test_first_load_rereads_the_draft_under_the_lock(factory: Factory) -> None:
    """Review finding (U2 code review): after taking the locks the Send
    tab's first load re-reads the draft, so a concurrent PUT's committed
    selection is not overwritten by the default selection."""
    app_id = await _seed_marcus(factory)
    async with factory() as db:
        db.add(
            QuotePackage(
                application_id=app_id, quote_ids=[], lo_edited=False, report_token="u2-draft"
            )
        )
        await db.commit()
    async with factory() as loader, factory() as editor:
        application = await loader.get(Application, app_id)
        assert application is not None
        # The loader's session already holds the untouched empty draft.
        before = (
            await loader.execute(select(QuotePackage).where(QuotePackage.application_id == app_id))
        ).scalar_one()
        assert before.quote_ids == [] and not before.lo_edited
        picked = (await _quotes(editor, app_id))[0].id
        edited = (
            await editor.execute(select(QuotePackage).where(QuotePackage.application_id == app_id))
        ).scalar_one()
        edited.quote_ids = [picked]
        edited.recommended_quote_id = picked
        edited.lo_edited = True
        await editor.commit()

        package = await get_or_create_package(loader, application)

        assert package.quote_ids == [picked]
        assert package.lo_edited


# --- lock_application vs FK inserts -------------------------------------------


async def test_activity_insert_is_not_blocked_by_the_application_lock(
    factory: Factory,
) -> None:
    """`lock_application` is `FOR NO KEY UPDATE`: another session's insert of
    a row referencing the application (its `FOR KEY SHARE`) goes through,
    and so does one referencing a locked quote or package."""
    app_id = await _seed_marcus(factory)
    async with factory() as holder, factory() as other:
        await lock_application_quotes(holder, app_id)
        await lock_application_packages(holder, app_id)
        locked = await lock_application(holder, app_id)
        assert locked.id == app_id

        await other.execute(text("SET LOCAL lock_timeout = '1s'"))
        other.add(
            ActivityEvent(
                application_id=app_id,
                actor="system",
                type="test.fk_insert",
                payload={},
                at=now(),
            )
        )
        await other.commit()  # raises LockNotAvailable if blocked
        await holder.commit()


async def test_lock_application_returns_the_committed_row(factory: Factory) -> None:
    """`populate_existing`: the returned row is the committed one, not the
    session's older copy."""
    app_id = await _seed_marcus(factory)
    async with factory() as reader, factory() as writer:
        stale_copy = await reader.get(Application, app_id)
        assert stale_copy is not None
        await writer.execute(
            text("UPDATE applications SET status = 'stale' WHERE id = :id"), {"id": app_id}
        )
        await writer.commit()
        locked = await lock_application(reader, app_id)
        assert locked is stale_copy
        assert locked.status is ApplicationStatus.STALE
        await reader.rollback()


# --- CQ-017 override + its activity event: one transaction (PR #34 m2) ----------


class _EventWriteFailed(RuntimeError):
    pass


@pytest.mark.parametrize("revert", [False, True])
async def test_override_and_its_event_commit_together(
    factory: Factory, monkeypatch: pytest.MonkeyPatch, revert: bool
) -> None:
    """A failure writing the field event rolls the override (or revert) and
    its stale marking back: nothing was committed before the event."""
    app_id = await _seed_marcus(factory)
    async with factory() as db:
        application = await db.get(Application, app_id)
        assert application is not None
        user = await db.get(User, application.lo_id)
        assert user is not None
        if revert:
            await enrichment_router.patch_field_value(
                app_id,
                FIELD,
                FieldValueOverrideRequest.model_validate({"value": "0.012"}),
                user,  # type: ignore[arg-type]
                db,
                application,
            )
    async with factory() as db:
        before_quotes = {q.id: q.stale for q in await _quotes(db, app_id)}
        before_row = (
            await db.execute(
                select(FieldValue.source, FieldValue.value).where(
                    FieldValue.application_id == app_id, FieldValue.field_key == FIELD
                )
            )
        ).one_or_none()
        before_stale_events = await _events(db, app_id, "quotes.marked_stale")

    async def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise _EventWriteFailed("event write failed")

    monkeypatch.setattr(enrichment_router, "record_field_event", _boom)
    async with factory() as db:
        application = await db.get(Application, app_id)
        user = await db.get(User, application.lo_id if application else None)
        with pytest.raises(_EventWriteFailed):
            if revert:
                await enrichment_router.revert_field_value_route(
                    app_id,
                    FIELD,
                    user,  # type: ignore[arg-type]
                    db,
                    application,  # type: ignore[arg-type]
                )
            else:
                await enrichment_router.patch_field_value(
                    app_id,
                    FIELD,
                    FieldValueOverrideRequest.model_validate({"value": "0.015"}),
                    user,  # type: ignore[arg-type]
                    db,
                    application,  # type: ignore[arg-type]
                )

    async with factory() as db:
        after_row = (
            await db.execute(
                select(FieldValue.source, FieldValue.value).where(
                    FieldValue.application_id == app_id, FieldValue.field_key == FIELD
                )
            )
        ).one_or_none()
        assert after_row == before_row
        assert {q.id: q.stale for q in await _quotes(db, app_id)} == before_quotes
        assert await _events(db, app_id, "quotes.marked_stale") == before_stale_events
        if not revert:
            assert before_row is None or before_row.source is not FieldSource.LO_OVERRIDE


async def test_override_commits_the_override_and_both_events(factory: Factory) -> None:
    app_id = await _seed_marcus(factory)
    async with factory() as db:
        application = await db.get(Application, app_id)
        assert application is not None
        user = await db.get(User, application.lo_id)
        assert user is not None
        result = await enrichment_router.patch_field_value(
            app_id,
            FIELD,
            FieldValueOverrideRequest.model_validate({"value": "0.012"}),
            user,  # type: ignore[arg-type]
            db,
            application,
        )
        assert result.source is FieldSource.LO_OVERRIDE
    async with factory() as db:
        assert await _events(db, app_id, "quotes.marked_stale") == 1
        assert await _events(db, app_id, "field.edited") == 1
        assert all(q.stale for q in await _quotes(db, app_id))
