"""The one lock module for an application's pricing and verification state
(CQ-028a review M1, CQ-018 review minor 4, P5/P6 merge decision M3).

Every write that must serialise per application -- verification-tab edits,
the pipeline's verify step, Quote Builder writes, CQ-017 field-value
overrides, Send-tab package writes, the send's `record` step, hard-pull
consent decisions and the borrower's report actions -- takes the row lock
from `lock_application`. The lock is held until the caller's transaction
ends.

Lock order (one order for the whole codebase, so no two writers can wait
on each other in a cycle):

    quotes  ->  quote packages / versions  ->  applications

- A writer that UPDATEs or DELETEs an application's existing quotes takes
  `lock_application_quotes` FIRST (reprice, Save & AutoQuote, the scenario
  PUT's stale marking, quote delete, CQ-017 override/revert stale marking,
  the CQ-033 hard pull). CQ-030's `mark_stale` locks every quote it may
  touch, ordered by id, in its first statement.
- A writer that changes an application's quote packages takes
  `lock_application_packages` (or locks the one package it acts on) after
  the quotes and before the application (Send-tab PUT/first load, quote
  recommend/delete and reprice, which edit the unsent draft; the borrower's
  report actions: package -> version -> application; the send's `freeze`:
  package -> version).
- `lock_application` comes last.

Every lock takes rows in id order, so two holders of the same kind never
cross either.

`FOR NO KEY UPDATE` (lock-hardening minor 3) for applications and quotes:
it still conflicts with itself and with `FOR UPDATE`, but not with the
`FOR KEY SHARE` lock Postgres takes on a referenced row for every insert
of a row that references it (`activity_events`, `flags`, `quotes.
scenario_id`, `applications.recommended_quote_id`, ...). With `FOR
UPDATE`, a holder waiting on another session that was inserting such a
row while waiting for the lock deadlocked. Packages keep `FOR UPDATE`, the
mode every other package lock (`freeze`, `start_send`, the report actions)
already takes.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.features.applications.models import Application
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage


async def lock_application(db: AsyncSession, application_id: uuid.UUID) -> Application:
    """Locks the `applications` row (`FOR NO KEY UPDATE`) until the current
    transaction ends and returns it re-read (`populate_existing`), so the
    caller decides from the committed row, not a stale in-session copy.
    404s when the application does not exist. Take it LAST (module doc)."""
    application = (
        await db.execute(
            select(Application)
            .where(Application.id == application_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    return application


async def lock_application_quotes(db: AsyncSession, application_id: uuid.UUID) -> None:
    """Locks every quote of the application (`FOR NO KEY UPDATE`, ordered
    by id) until the transaction ends. Take it FIRST, before the packages
    and the application (module doc)."""
    await db.execute(
        select(Quote.id)
        .join(Scenario, Quote.scenario_id == Scenario.id)
        .where(Scenario.application_id == application_id)
        .order_by(Quote.id)
        .with_for_update(of=Quote, key_share=True)
    )


async def lock_application_packages(db: AsyncSession, application_id: uuid.UUID) -> None:
    """Locks every quote package of the application (`FOR UPDATE`, ordered
    by id) until the transaction ends. Take it after the quotes and before
    the application (module doc)."""
    await db.execute(
        select(QuotePackage.id)
        .where(QuotePackage.application_id == application_id)
        .order_by(QuotePackage.id)
        .with_for_update()
    )
