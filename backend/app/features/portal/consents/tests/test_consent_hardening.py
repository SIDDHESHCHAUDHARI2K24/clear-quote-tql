"""CQ-033 hardening round: request lock, accept lock order (m1), text-hash
proof (m2), expiry race (m3) and provider failure (m4), on the seeded Tom &
Lisa Brandt persona."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.enums import UserRole
from app.features.auth.models import User
from app.features.borrower.consent.models import Consent, ConsentStatus
from app.features.portal.consents import service
from app.integrations.common.failure_toggle import set_forced_failure
from app.integrations.credit.models import CreditPullType, ProviderCreditReport

from .test_consents_api import (
    MakeBorrower,
    MakeStaff,
    _accept_body,
    _client_of,
    _events,
    _freeze,
    _hard_pull_calls,
    _request,
    _seed,
    sent,  # noqa: F401  (fixture)
)


@pytest.fixture
def statements(test_engine: AsyncEngine) -> Iterator[list[str]]:
    """Every SQL statement run on the test engine while the test runs."""
    seen: list[str] = []

    def _record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        seen.append(" ".join(statement.split()))

    event.listen(test_engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", _record)


def _index(statements: list[str], predicate: Any) -> int:
    return next(i for i, stmt in enumerate(statements) if predicate(stmt))


async def test_request_hard_pull_takes_no_second_for_update(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    sent: list[dict[str, str]],  # noqa: F811
    statements: list[str],
) -> None:
    """The router's `lock_application` (`FOR NO KEY UPDATE`) is the only
    application lock: no `FOR UPDATE` upgrade (FK key-share deadlock risk),
    and the 409-while-pending check still holds under that lock."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    statements.clear()

    await _request(client, brandt)

    locks = [stmt for stmt in statements if " FOR " in stmt and "UPDATE" in stmt.split(" FOR ")[-1]]
    assert locks and all("FOR NO KEY UPDATE" in stmt for stmt in locks), locks
    again = await client.post(f"/api/v1/applications/{brandt.id}/credit/hard-pull-request")
    assert again.status_code == 409


async def test_accept_locks_quotes_before_the_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],  # noqa: F811
    statements: list[str],
) -> None:
    """m1: the accept path takes the quotes lock, then the application lock,
    then UPDATEs quotes (bucket crossing) -- CQ-030's `mark_stale` order
    (quotes -> versions -> applications), so the two cannot invert."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await db_session.execute(
        update(ProviderCreditReport)
        .where(
            ProviderCreditReport.loan_number == brandt.los_loan_guid,
            ProviderCreditReport.pull_type == CreditPullType.HARD_PULL,
        )
        .values(experian_score=675, equifax_score=670, transunion_score=680, middle_score=675)
    )
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    statements.clear()

    accepted = await client.post(
        f"/api/v1/portal/consents/{consent_id}/accept", json=_accept_body("Tom Brandt")
    )

    assert accepted.status_code == 200, accepted.text
    quotes_lock = _index(statements, lambda s: "FOR UPDATE OF quotes" in s)
    app_lock = _index(statements, lambda s: "FROM applications" in s and "FOR NO KEY UPDATE" in s)
    quotes_update = _index(statements, lambda s: s.startswith("UPDATE quotes"))
    assert quotes_lock < app_lock < quotes_update


async def test_accept_rejects_a_changed_text(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],  # noqa: F811
) -> None:
    """m2: the accept must carry the version and SHA-256 of the text the
    borrower saw; a mismatch is 409 CONSENT_TEXT_CHANGED and nothing is
    recorded or pulled."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    url = f"/api/v1/portal/consents/{consent_id}/accept"
    good = _accept_body("Tom Brandt")

    wrong_hash = await client.post(url, json={**good, "text_sha256": "0" * 64})
    wrong_version = await client.post(url, json={**good, "text_version": "hard_pull_v0"})
    missing = await client.post(url, json={"typed_name": "Tom Brandt"})

    for response in (wrong_hash, wrong_version):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONSENT_TEXT_CHANGED"
    assert missing.status_code == 422
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None and row.status is ConsentStatus.PENDING and row.text_hash is None
    assert await _hard_pull_calls(db_session, brandt.los_loan_guid) == 0

    ok = await client.post(url, json=good)
    assert ok.status_code == 200, ok.text
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None and row.text_hash == good["text_sha256"]


@pytest.mark.parametrize("decided", [ConsentStatus.ACCEPTED, ConsentStatus.DECLINED])
async def test_expiry_never_overwrites_a_decision(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    sent: list[dict[str, str]],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    decided: ConsentStatus,
) -> None:
    """m3: a reader holding a stale `pending` copy past `expires_at` must not
    overwrite a decision another request committed in between."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    stale = await db_session.get(Consent, consent_id)
    assert stale is not None and stale.requested_at is not None
    assert stale.status is ConsentStatus.PENDING
    _freeze(monkeypatch, stale.requested_at + timedelta(days=15))
    # The decision lands in the database behind the stale in-memory copy.
    await db_session.execute(
        update(Consent)
        .where(Consent.id == consent_id)
        .values(status=decided)
        .execution_options(synchronize_session=False)
    )
    assert stale.status is ConsentStatus.PENDING

    row, expired = await service._expire_if_due(db_session, stale)

    assert expired is False
    assert row.status is decided


async def test_provider_failure_keeps_the_request_pending(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],  # noqa: F811
) -> None:
    """m4: the bureau is down -> 502; the decision is rolled back (pending,
    retryable), a `credit.hard_pull_failed` event and one LO email are
    committed; a retry once the bureau is back pulls once."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    # The service's rollback must only undo the request's own writes.
    await db_session.commit()
    sent.clear()
    url = f"/api/v1/portal/consents/{consent_id}/accept"
    await set_forced_failure("credit", True)

    failed = await client.post(url, json=_accept_body("Tom Brandt"))

    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    # The service rolled the shared test session back, expiring its objects.
    await db_session.refresh(brandt)
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None and row.status is ConsentStatus.PENDING and row.typed_name is None
    failures = await _events(db_session, brandt, "credit.hard_pull_failed")
    assert len(failures) == 1
    payload: Any = failures[0].payload
    assert payload["consent_id"] == str(consent_id)
    assert payload["error_code"] == "PROVIDER_UNAVAILABLE"
    assert await _events(db_session, brandt, "credit.consent_accepted") == []
    assert await _events(db_session, brandt, "credit.hard_pull_completed") == []
    lo = await db_session.get(User, brandt.lo_id)
    assert lo is not None
    assert [(mail["to"], mail["subject"]) for mail in sent] == [
        (lo.email, "Credit check could not be completed")
    ]

    # A second failed attempt is recorded, but the LO is not emailed again.
    again = await client.post(url, json=_accept_body("Tom Brandt"))
    assert again.status_code == 502
    await db_session.refresh(brandt)
    assert len(await _events(db_session, brandt, "credit.hard_pull_failed")) == 2
    assert len(sent) == 1

    await set_forced_failure("credit", False)
    retry = await client.post(url, json=_accept_body("Tom Brandt"))

    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "accepted"
    assert len(await _events(db_session, brandt, "credit.hard_pull_completed")) == 1
