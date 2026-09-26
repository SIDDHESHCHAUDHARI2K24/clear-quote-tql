"""CQ-030 stale quote job (spec.md "Scope", plan.md decisions #1-#10).

`mark_stale(db, now)` is the one idempotent job body. The Temporal
activity (`app/workflows/stale_quote_check.py`) and the admin endpoint
(`POST /api/v1/admin/jobs/stale-check`) both call it. `now` is always
passed in; nothing here reads the clock except `clear_stale`, whose `now`
(used only for its event's `at`) defaults to `core/clock.now()` for
request-path callers (CQ-018 reprice). See `clear_stale` for its contract.

Steps (spec.md):
1. Quotes with `priced_at < now - stale_days` -> `stale = true`.
2. Sent versions with `expires_at < now` -> `expired_at = now` (once).
3. Priced/Sent/Viewed applications whose deciding quote is older than
   `stale_days`, or (Sent/Viewed only) whose latest sent version has
   expired -> status Stale, one activity event, and their quotes flagged
   (those past the cutoff plus those the expired version showed).
   Inquiry/OptionSelected keep their status; the same quotes are flagged.
   Candidate rows are locked `FOR NO KEY UPDATE` and decided from the
   locked row. Lock order: quotes (all of them, by id, first) -> versions
   -> applications, the one order of `applications/locking.py`.
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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, Select, func, or_, select, update
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
    db: AsyncSession,
    application_id: uuid.UUID,
    reason: str,
    *,
    older_than: datetime | None = None,
    quote_ids: Sequence[uuid.UUID] | None = None,
    priced_by: datetime | None = None,
) -> list[uuid.UUID]:
    """The one stale path (E12, merge plan M4): flags not-yet-stale quotes of
    one application `stale = true` and returns the ids it changed (sorted).
    It writes no activity event and never changes the application's status
    -- every caller decides both and writes exactly one event of its own:
    `mark_stale` (`application.stale`), CQ-033's FICO-bucket re-run
    (`credit.hard_pull_completed`), CQ-017's override/revert
    (`quotes.marked_stale`) and CQ-018's scenario PUT (`scenario.updated`).
    `reason` is logged for traceability.

    With neither `older_than` nor `quote_ids` every quote is flagged (the
    CQ-033 and CQ-017 case). With either, only quotes with `priced_at <
    older_than` OR `id` in `quote_ids` are flagged (review m5: an expired
    sent version flags the quotes it showed plus genuinely old ones, never
    a fresh quote the LO priced since). `priced_by` narrows the `quote_ids`
    arm to quotes priced at or before that instant -- `mark_stale` passes
    the expired version's `sent_at`, so a quote a re-price refreshed in
    place after the send (same id, still in the old snapshot) is not
    flagged again (CQ-030 plan.md #17a, resolved in U3)."""
    conditions: list[ColumnElement[bool]] = [
        Quote.id.in_(_application_quote_ids(application_id)),
        Quote.stale.is_(False),
    ]
    if older_than is not None or quote_ids is not None:
        restrict: list[ColumnElement[bool]] = []
        if older_than is not None:
            restrict.append(Quote.priced_at < older_than)
        if quote_ids:
            listed = Quote.id.in_(list(quote_ids))
            restrict.append(
                listed if priced_by is None else listed & (Quote.priced_at <= priced_by)
            )
        if not restrict:
            return []
        conditions.append(or_(*restrict))
    result = await db.execute(
        update(Quote)
        .where(*conditions)
        .values(stale=True)
        .returning(Quote.id)
        .execution_options(synchronize_session="fetch")
    )
    changed = sorted(result.scalars().all())
    if changed:
        logger.info(
            "Marked %d quote(s) stale for application %s (%s)", len(changed), application_id, reason
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


@dataclass(frozen=True)
class _LatestVersion:
    expires_at: datetime
    sent_at: datetime
    quote_ids: tuple[uuid.UUID, ...]


def _version_quote_ids(
    snapshot: object, package_quote_ids: Sequence[uuid.UUID] | None
) -> tuple[uuid.UUID, ...]:
    """The quotes a sent version showed: its frozen snapshot's options
    (CQ-021 `ReportViewModel.options[].quote_id`), falling back to the
    package's `quote_ids` when the snapshot carries none."""
    ids: list[uuid.UUID] = []
    options = snapshot.get("options") if isinstance(snapshot, dict) else None
    if isinstance(options, list):
        for option in options:
            raw = option.get("quote_id") if isinstance(option, dict) else None
            try:
                ids.append(uuid.UUID(str(raw)))
            except ValueError:
                continue
    if not ids and package_quote_ids:
        ids = list(package_quote_ids)
    return tuple(ids)


async def _latest_versions(
    db: AsyncSession, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, _LatestVersion]:
    """Per application: `expires_at` and quote ids of its most recently
    sent version."""
    if not application_ids:
        return {}
    rows = await db.execute(
        select(
            QuotePackage.application_id,
            QuotePackageVersion.expires_at,
            QuotePackageVersion.sent_at,
            QuotePackageVersion.snapshot,
            QuotePackage.quote_ids,
        )
        .join(QuotePackageVersion, QuotePackageVersion.package_id == QuotePackage.id)
        .where(QuotePackage.application_id.in_(application_ids))
        .ext(distinct_on(QuotePackage.application_id))
        .order_by(
            QuotePackage.application_id,
            QuotePackageVersion.sent_at.desc(),
            QuotePackageVersion.version.desc(),
        )
    )
    return {
        app_id: _LatestVersion(expires_at, sent_at, _version_quote_ids(snapshot, package_quote_ids))
        for app_id, expires_at, sent_at, snapshot, package_quote_ids in rows.all()
    }


async def _move_to_stale(
    db: AsyncSession,
    application: Application,
    *,
    now: datetime,
    stale_days: int,
    reason: str,
) -> bool:
    """Conditional status UPDATE; writes the one activity event only when it
    matched (so a concurrent or repeated run never writes a second one).
    `application` is the row `mark_stale` locked (`FOR NO KEY UPDATE`), so its
    status is the committed one and no concurrent writer can change it."""
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
    # Lock first (U2, applications/locking.py): every quote this run may
    # update -- the ones past the cutoff and every quote of a step-3
    # candidate -- in one statement ordered by id, so the job takes its
    # quote locks in the same id order as every per-application writer
    # (`lock_application_quotes`) and before any version or application.
    # Then update only locked rows.
    candidate_statuses = (*_MOVES_TO_STALE, *_KEEPS_STATUS)
    locked_rows = (
        await db.execute(
            select(Quote.id, Scenario.application_id, Application.status)
            .join(Scenario, Quote.scenario_id == Scenario.id)
            .join(Application, Scenario.application_id == Application.id)
            .where(
                or_(
                    (Quote.priced_at < cutoff) & Quote.stale.is_(False),
                    Application.status.in_(candidate_statuses),
                )
            )
            .order_by(Quote.id)
            .with_for_update(of=Quote, key_share=True)
        )
    ).all()
    locked_ids = [quote_id for quote_id, _app_id, _status in locked_rows]
    # Applications whose quotes step 1 already holds (review minor a, U3).
    locked_candidates = {
        app_id for _quote_id, app_id, status in locked_rows if status in candidate_statuses
    }
    if locked_ids:
        marked = await db.execute(
            update(Quote)
            .where(
                Quote.id.in_(locked_ids),
                Quote.priced_at < cutoff,
                Quote.stale.is_(False),
            )
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

    # Step 3: application status. Lock every candidate row (ordered by id,
    # so two concurrent runs lock in the same order) and decide from the
    # locked row's status (review m2). Lock order across the whole job is
    # quotes (step 1) -> versions (step 2) -> applications (here): the same
    # version-before-application order the portal paths use (CQ-022 report
    # view: version then application; CQ-024 actions: package, version,
    # application) and `clear_stale`'s quotes-before-application. The job
    # never locks a package, so it cannot close a cycle with those paths.
    # Step 3 updates candidates' quotes after locking the applications;
    # step 1 already locked them. This re-lock only covers applications that
    # were *not* candidates at step 1 (their status changed since), so it
    # never waits on a quote a writer inserted mid-job into an application
    # step 1 already holds (U3, review minor a): such a quote is fresh, so
    # step 3's conditional UPDATE skips it without locking it.
    # `FOR NO KEY UPDATE` throughout (applications/locking.py): an insert
    # referencing a locked row (an activity event, say) is not blocked.
    relock = (
        select(Quote.id)
        .join(Scenario, Quote.scenario_id == Scenario.id)
        .join(Application, Scenario.application_id == Application.id)
        .where(Application.status.in_(candidate_statuses))
        .order_by(Quote.id)
        .with_for_update(of=Quote, key_share=True)
    )
    if locked_candidates:
        relock = relock.where(Scenario.application_id.not_in(locked_candidates))
    await db.execute(relock)
    candidates = list(
        (
            await db.execute(
                select(Application)
                .where(Application.status.in_(candidate_statuses))
                .order_by(Application.id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    deciding = await _deciding_quote_priced_at(
        db, [a for a in candidates if a.status in _MOVES_TO_STALE]
    )
    latest_versions = await _latest_versions(
        db, [a.id for a in candidates if a.status in (*_VERSION_CHECKED, *_KEEPS_STATUS)]
    )

    for application in candidates:
        latest = latest_versions.get(application.id)
        version_expired = latest is not None and latest.expires_at < now
        # Review m5: flag only the quotes the expired version showed plus
        # quotes already past the cutoff -- never a fresh quote priced since.
        sent_quote_ids = latest.quote_ids if latest is not None and version_expired else ()
        # #17a (U3): a sent quote re-priced in place since the send keeps its
        # fresh flag -- only quotes priced by the version's `sent_at` count.
        sent_by = latest.sent_at if latest is not None else None

        if application.status in _KEEPS_STATUS:
            if version_expired:
                flagged = await mark_application_quotes_stale(
                    db,
                    application.id,
                    REASON_VERSION_EXPIRED,
                    older_than=cutoff,
                    quote_ids=sent_quote_ids,
                    priced_by=sent_by,
                )
                result.quotes_marked_stale += len(flagged)
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
            flagged = await mark_application_quotes_stale(
                db,
                application.id,
                reason,
                older_than=cutoff,
                quote_ids=sent_quote_ids,
                priced_by=sent_by,
            )
            result.quotes_marked_stale += len(flagged)

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
    db: AsyncSession,
    application_id: uuid.UUID,
    *,
    fresh_quote_ids: Sequence[uuid.UUID],
    now: datetime | None = None,
) -> bool:
    """Called after a successful re-price (CQ-018's `/reprice`, E12).

    Contract for CQ-018:
    - Pass `fresh_quote_ids`: the ids of the quotes the re-price just wrote
      or refreshed. Only those lose their `stale` flag (ids that do not
      belong to `application_id` are ignored). No time window is used, so
      the result does not depend on the clock (review M1/m3); superseded
      quotes keep their flag.
    - When at least one fresh quote belongs to the application and it is
      Stale, it moves Stale -> Priced (conditional UPDATE) and one
      `application.repriced_from_stale` event is written at `now`
      (default `core/clock.now()`). Other statuses are left alone.
    - Returns whether the status moved. Empty `fresh_quote_ids` is a no-op
      returning False.
    - Flushes; the caller commits (in the same transaction as the re-price).

    Callers (U3): CQ-018's `reprice_application` and `autoquote_replacing`,
    under their quotes -> packages -> application locks. Pricing's
    `priced_at` and send's `sent_at` read `core/clock.now()` too (M5), so a
    `CLOCK_NOW` demo re-prices cleanly."""
    ids = list(dict.fromkeys(fresh_quote_ids))
    if not ids:
        return False
    resolved_now = now if now is not None else clock.now()

    fresh = await db.execute(
        update(Quote)
        .where(
            Quote.id.in_(ids),
            Quote.id.in_(_application_quote_ids(application_id)),
        )
        .values(stale=False)
        .returning(Quote.id)
        .execution_options(synchronize_session="fetch")
    )
    if not fresh.all():
        return False

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
