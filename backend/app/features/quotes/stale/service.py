"""CQ-030 stale quote job (spec.md "Scope", plan.md decisions #1-#10).

`mark_stale(db, now)` is the one idempotent job body. The Temporal
activity (`app/workflows/stale_quote_check.py`) and the admin endpoint
(`POST /api/v1/admin/jobs/stale-check`) both call it. `now` is always
passed in; nothing here reads the clock except `clear_stale`, whose `now`
defaults to `core/clock.now()` for request-path callers (CQ-018 reprice).

Steps (spec.md):
1. Quotes with `priced_at < now - stale_days` -> `stale = true`.
2. Sent versions with `expires_at < now` -> `expired_at = now` (once).
3. Priced/Sent/Viewed applications whose deciding quote is older than
   `stale_days`, or (Sent/Viewed only) whose latest sent version has
   expired -> status Stale, their quotes flagged, one activity event.
   Inquiry/OptionSelected keep their status; their quotes are flagged.
4. A second run at the same `now` changes nothing and writes no events.
   Every write is conditional on the row not already being in the target
   state, and an event is written only when the conditional status UPDATE
   actually matched the row.

The flush/commit boundary belongs to the caller: these functions flush,
never commit.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from app.features.quotes.stale.schemas import StaleResult
from app.features.settings.models import Setting

logger = logging.getLogger(__name__)

STALE_QUOTE_DAYS_KEY = "stale_quote_days"
DEFAULT_STALE_QUOTE_DAYS = 21

EVENT_APPLICATION_STALE = "application.stale"
EVENT_REPRICED_FROM_STALE = "application.repriced_from_stale"
_ACTOR_SYSTEM = "system"

REASON_QUOTE_AGE = "quote_age"
REASON_VERSION_EXPIRED = "version_expired"

_MOVES_TO_STALE = (ApplicationStatus.PRICED, ApplicationStatus.SENT, ApplicationStatus.VIEWED)
_VERSION_CHECKED = (ApplicationStatus.SENT, ApplicationStatus.VIEWED)
_KEEPS_STATUS = (ApplicationStatus.INQUIRY, ApplicationStatus.OPTION_SELECTED)


async def get_stale_quote_days(db: AsyncSession) -> int:
    """`settings.stale_quote_days` (seeded 21), falling back to 21 when the
    row is missing or not an integer."""
    row = await db.get(Setting, STALE_QUOTE_DAYS_KEY)
    if row is None or row.value is None:
        return DEFAULT_STALE_QUOTE_DAYS
    try:
        return int(row.value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        logger.warning("Setting %s=%r is not an integer; using 21", STALE_QUOTE_DAYS_KEY, row.value)
        return DEFAULT_STALE_QUOTE_DAYS


def _application_quote_ids(application_id: uuid.UUID) -> Select[uuid.UUID]:
    return (
        select(Quote.id)
        .join(Scenario, Quote.scenario_id == Scenario.id)
        .where(Scenario.application_id == application_id)
    )


async def mark_application_quotes_stale(
    db: AsyncSession, application_id: uuid.UUID, reason: str
) -> int:
    """Shared helper (E12): flags every not-yet-stale quote of one
    application `stale = true` and returns how many changed. It writes no
    activity event and never changes the application's status -- callers
    (`mark_stale`, CQ-033's FICO-bucket re-run) decide both. `reason` is
    logged for traceability."""
    result = await db.execute(
        update(Quote)
        .where(Quote.id.in_(_application_quote_ids(application_id)), Quote.stale.is_(False))
        .values(stale=True)
        .returning(Quote.id)
        .execution_options(synchronize_session="fetch")
    )
    changed = len(result.all())
    if changed:
        logger.info(
            "Marked %d quote(s) stale for application %s (%s)", changed, application_id, reason
        )
    return changed


async def _deciding_quote_priced_at(
    db: AsyncSession, applications: list[Application]
) -> dict[uuid.UUID, datetime]:
    """Per application: the most recent `priced_at` among its quotes, which
    is never older than the recommended quote's (plan.md #3). Using the
    newest rather than the recommended quote alone means a re-price that
    writes new quotes without repointing `recommended_quote_id` does not
    flip the application back to Stale on the next run (CQ-030 review)."""
    ids = [a.id for a in applications]
    if not ids:
        return {}
    rows = await db.execute(
        select(Scenario.application_id, func.max(Quote.priced_at))
        .join(Quote, Quote.scenario_id == Scenario.id)
        .where(Scenario.application_id.in_(ids))
        .group_by(Scenario.application_id)
    )
    return {app_id: at for app_id, at in rows.all()}


async def _latest_version_expires_at(
    db: AsyncSession, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """Per application: `expires_at` of its most recently sent version."""
    if not application_ids:
        return {}
    rows = await db.execute(
        select(QuotePackage.application_id, QuotePackageVersion.expires_at)
        .join(QuotePackageVersion, QuotePackageVersion.package_id == QuotePackage.id)
        .where(QuotePackage.application_id.in_(application_ids))
        .ext(distinct_on(QuotePackage.application_id))
        .order_by(
            QuotePackage.application_id,
            QuotePackageVersion.sent_at.desc(),
            QuotePackageVersion.version.desc(),
        )
    )
    return {app_id: expires_at for app_id, expires_at in rows.all()}


async def _move_to_stale(
    db: AsyncSession,
    application: Application,
    *,
    now: datetime,
    stale_days: int,
    reason: str,
) -> bool:
    """Conditional status UPDATE; writes the one activity event only when it
    matched (so a concurrent or repeated run never writes a second one)."""
    from_status = application.status
    moved = await db.execute(
        update(Application)
        .where(Application.id == application.id, Application.status.in_(_MOVES_TO_STALE))
        .values(status=ApplicationStatus.STALE)
        .returning(Application.id)
        .execution_options(synchronize_session="fetch")
    )
    if moved.first() is None:
        return False
    db.add(
        ActivityEvent(
            application_id=application.id,
            actor=_ACTOR_SYSTEM,
            type=EVENT_APPLICATION_STALE,
            payload={
                "message": f"Quotes older than {stale_days} days",
                "from_status": from_status.value,
                "reason": reason,
            },
            at=now,
        )
    )
    return True


async def mark_stale(db: AsyncSession, now: datetime) -> StaleResult:
    """The stale job body (spec.md steps 1-4). Flushes; the caller commits."""
    stale_days = await get_stale_quote_days(db)
    cutoff = now - timedelta(days=stale_days)
    result = StaleResult()

    # Step 1: strict boundary -- stale only when age > stale_days.
    marked = await db.execute(
        update(Quote)
        .where(Quote.priced_at < cutoff, Quote.stale.is_(False))
        .values(stale=True)
        .returning(Quote.id)
        .execution_options(synchronize_session="fetch")
    )
    result.quotes_marked_stale += len(marked.all())

    # Step 2: sent versions past `expires_at` -> expired (stamped once).
    expired = await db.execute(
        update(QuotePackageVersion)
        .where(QuotePackageVersion.expires_at < now, QuotePackageVersion.expired_at.is_(None))
        .values(expired_at=now)
        .returning(QuotePackageVersion.id)
        .execution_options(synchronize_session="fetch")
    )
    result.versions_expired += len(expired.all())

    # Step 3: application status.
    candidates = list(
        (
            await db.execute(
                select(Application).where(
                    Application.status.in_((*_MOVES_TO_STALE, *_KEEPS_STATUS))
                )
            )
        )
        .scalars()
        .all()
    )
    deciding = await _deciding_quote_priced_at(
        db, [a for a in candidates if a.status in _MOVES_TO_STALE]
    )
    version_expiry = await _latest_version_expires_at(
        db, [a.id for a in candidates if a.status in (*_VERSION_CHECKED, *_KEEPS_STATUS)]
    )

    for application in candidates:
        expires_at = version_expiry.get(application.id)
        version_expired = expires_at is not None and expires_at < now

        if application.status in _KEEPS_STATUS:
            if version_expired:
                result.quotes_marked_stale += await mark_application_quotes_stale(
                    db, application.id, REASON_VERSION_EXPIRED
                )
            continue

        priced_at = deciding.get(application.id)
        quote_too_old = priced_at is not None and priced_at < cutoff
        version_too_old = application.status in _VERSION_CHECKED and version_expired
        if not (quote_too_old or version_too_old):
            continue

        reason = REASON_QUOTE_AGE if quote_too_old else REASON_VERSION_EXPIRED
        if await _move_to_stale(db, application, now=now, stale_days=stale_days, reason=reason):
            result.applications_marked_stale += 1
            result.application_ids.append(str(application.id))
            result.quotes_marked_stale += await mark_application_quotes_stale(
                db, application.id, reason
            )

    await db.flush()
    logger.info(
        "mark_stale(now=%s, stale_days=%d): %d quotes, %d versions, %d applications",
        now.isoformat(),
        stale_days,
        result.quotes_marked_stale,
        result.versions_expired,
        result.applications_marked_stale,
    )
    return result


async def clear_stale(
    db: AsyncSession, application_id: uuid.UUID, *, now: datetime | None = None
) -> bool:
    """Called after a successful re-price (CQ-018's `/reprice`, E12).

    Clears `stale` on the application's quotes priced inside the window
    (the ones the re-price just wrote or refreshed) and moves the
    application Stale -> Priced with one `application.repriced_from_stale`
    event. Older quotes keep their flag, so the next `mark_stale` run finds
    nothing to change. Returns whether the status moved. Flushes; the
    caller commits."""
    resolved_now = now if now is not None else clock.now()
    cutoff = resolved_now - timedelta(days=await get_stale_quote_days(db))

    await db.execute(
        update(Quote)
        .where(
            Quote.id.in_(_application_quote_ids(application_id)),
            Quote.stale.is_(True),
            Quote.priced_at >= cutoff,
        )
        .values(stale=False)
        .execution_options(synchronize_session="fetch")
    )
    moved = await db.execute(
        update(Application)
        .where(Application.id == application_id, Application.status == ApplicationStatus.STALE)
        .values(status=ApplicationStatus.PRICED)
        .returning(Application.id)
        .execution_options(synchronize_session="fetch")
    )
    did_move = moved.first() is not None
    if did_move:
        db.add(
            ActivityEvent(
                application_id=application_id,
                actor=_ACTOR_SYSTEM,
                type=EVENT_REPRICED_FROM_STALE,
                payload={"message": "Re-priced; quotes are current again"},
                at=resolved_now,
            )
        )
    await db.flush()
    return did_move
