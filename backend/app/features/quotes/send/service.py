"""Quote package draft service (CQ-019).

One working package per application (D2; plan.md Decision 2): the newest
`quote_packages` row. The first `GET` creates the default draft under the
application's write lock, so two concurrent first loads never create two.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import scope_applications
from app.core.errors import NotFoundError, ValidationAppError
from app.features.applications.locks import lock_application
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.report.schemas import ReportViewModel
from app.features.quotes.send.default_draft import (
    MAX_PACKAGE_QUOTES,
    default_package_selection,
    draft_recommendation_text,
)
from app.features.quotes.send.models import QuotePackage
from app.features.quotes.send.readiness import package_blockers
from app.features.quotes.send.schemas import (
    PackageRead,
    PackageReadiness,
    PackageUpdate,
    ReadinessBlocker,
)
from app.features.quotes.send.view_model import (
    build_package_view_model,
    current_recommendation_text,
    load_package_context,
    strategy_type,
)

PREVIEW_EXPIRY_DAYS = 21
"""Same as `portal/reports/versions.REPORT_EXPIRY_DAYS`: the preview shows
the expiry the borrower would see if the LO sent now."""

LETTER_ATTACHMENT = "Pre-approval letter (PDF)"

_ACTOR_SYSTEM = "system"
"""`ActivityEvent.actor`: "a user id (as string) or the literal `system`"."""


async def _newest_package(db: AsyncSession, application_id: uuid.UUID) -> QuotePackage | None:
    return (
        await db.execute(
            select(QuotePackage)
            .where(QuotePackage.application_id == application_id)
            .order_by(QuotePackage.created_at.desc(), QuotePackage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def recommendation_text_for(
    db: AsyncSession, application: Application, recommended_quote_id: uuid.UUID | None
) -> str | None:
    if recommended_quote_id is None:
        return None
    quote = await db.get(Quote, recommended_quote_id)
    if quote is None:
        return None
    scenario = await db.get(Scenario, quote.scenario_id)
    assert scenario is not None
    return draft_recommendation_text(quote, scenario, strategy_type(application))


async def _apply_default_selection(
    db: AsyncSession, application: Application, package: QuotePackage
) -> None:
    """Fills `package` from `default_package_selection` and keeps
    `applications.recommended_quote_id` in step, exactly as a brand-new
    default draft does. Shared by `new_default_package` and, for an unsent
    draft that predates any priced quote, `get_or_create_package` (code
    review M5)."""
    selection = await default_package_selection(db, application)
    package.quote_ids = selection.quote_ids
    package.recommended_quote_id = selection.recommended_quote_id
    package.recommendation_text = await recommendation_text_for(
        db, application, selection.recommended_quote_id
    )
    # One recommendation per application (plan.md Decision 8): the default
    # draft's pick becomes the application's when it had none (code review #4).
    if application.recommended_quote_id is None and selection.recommended_quote_id is not None:
        application.recommended_quote_id = selection.recommended_quote_id
        # code review M4: this is a server-side pick, not an LO action --
        # log it like `update_package`/`recommend_quote` do, so the
        # timeline explains where the recommendation came from.
        db.add(
            ActivityEvent(
                application_id=application.id,
                actor=_ACTOR_SYSTEM,
                type="quote.recommended",
                payload={
                    "quote_id": str(selection.recommended_quote_id),
                    "previous_quote_id": None,
                    "source": "default_draft",
                },
                at=datetime.now(UTC),
            )
        )


async def new_default_package(db: AsyncSession, application: Application) -> QuotePackage:
    """Builds (and flushes) the default draft; the caller commits. Also used
    by the seed's `apply_send_fixture`, so seeded packages follow the same
    rule."""
    # `quote_ids`/`lo_edited` start out explicit, not unset:
    # `_apply_default_selection` below runs a query first
    # (`default_package_selection`), and a query autoflushes this pending
    # INSERT -- both are NOT NULL, so they must already be valid values
    # before that happens.
    package = QuotePackage(
        application_id=application.id,
        quote_ids=[],
        lo_edited=False,
        report_token=secrets.token_urlsafe(24),
    )
    db.add(package)
    await _apply_default_selection(db, application, package)
    await db.flush()
    return package


def _unsent_drafts_stmt(application_id: uuid.UUID | None = None) -> Select[Any]:
    stmt = select(QuotePackage).where(QuotePackage.sent_at.is_(None))
    if application_id is not None:
        stmt = stmt.where(QuotePackage.application_id == application_id)
    return stmt.with_for_update()


async def drop_quote_from_drafts(
    db: AsyncSession, quote_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID | None] | None:
    """Called by the Quote Builder before it deletes a quote: an unsent
    draft never blocks a delete (code review #2); the quote just leaves the
    draft.

    Only hands the recommendation to the first quote left when the deleted
    quote *was* the draft's recommendation -- an LO who deliberately left
    no recommendation must not get one auto-assigned by an unrelated delete
    (code review M4). Returns the touched draft's
    `(application_id, recommended_quote_id)` when its recommendation
    changed, so the caller (`_delete_quote_row`) can keep
    `applications.recommended_quote_id` in step instead of disagreeing with
    it; `None` when no draft's recommendation changed."""
    drafts = (
        await db.execute(
            _unsent_drafts_stmt().where(
                or_(
                    QuotePackage.recommended_quote_id == quote_id,
                    QuotePackage.quote_ids.contains([quote_id]),
                )
            )
        )
    ).scalars()
    followed: tuple[uuid.UUID, uuid.UUID | None] | None = None
    for package in drafts:
        remaining = [q for q in package.quote_ids if q != quote_id]
        package.quote_ids = remaining
        if package.recommended_quote_id == quote_id:
            package.recommended_quote_id = remaining[0] if remaining else None
            followed = (package.application_id, package.recommended_quote_id)
    await db.flush()
    return followed


async def sync_draft_recommendation(
    db: AsyncSession, application_id: uuid.UUID, quote_id: uuid.UUID
) -> None:
    """Called by the Quote Builder's star: the unsent draft follows the
    application's recommendation (code review #4). A quote not yet in the
    draft goes first, keeping at most `MAX_PACKAGE_QUOTES`."""
    for package in (await db.execute(_unsent_drafts_stmt(application_id))).scalars():
        ids = [q for q in package.quote_ids if q != quote_id]
        package.quote_ids = (
            [quote_id, *ids][:MAX_PACKAGE_QUOTES]
            if quote_id not in package.quote_ids
            else list(package.quote_ids)
        )
        package.recommended_quote_id = quote_id
    await db.flush()


def _is_untouched_empty_draft(package: QuotePackage) -> bool:
    """M5's empty draft (created before any quote existed) vs. one the LO
    emptied on purpose (unticked every quote and saved `quote_ids: []`) --
    only the former should get refilled. `lo_edited` (post-merge review,
    code-review follow-up on M5) is set for good the first time
    `update_package` runs; a timestamp comparison was tried first and
    dropped -- Postgres's `now()` is transaction-start time, so `created_at
    == updated_at` can't tell a create and a later write apart when both
    land in the same transaction, as they do under this codebase's
    `db_session` test fixture."""
    return not package.quote_ids and not package.lo_edited


async def get_or_create_package(db: AsyncSession, application: Application) -> QuotePackage:
    """Decision 2: the newest `quote_packages` row is the working package,
    creating the default draft on the first call.

    Code review M5: the Send tab can be opened before any quote is priced,
    leaving an unsent draft with `quote_ids=[]` forever -- once quotes
    exist, re-apply the default to that *untouched* empty draft instead of
    returning it empty. An LO-emptied draft (`_is_untouched_empty_draft`
    is false once it's had any write) is left alone."""
    package = await _newest_package(db, application.id)
    if package is not None and (
        package.sent_at is not None or not _is_untouched_empty_draft(package)
    ):
        return package
    application = await lock_application(db, application.id)
    package = await _newest_package(db, application.id)
    if package is None:
        package = await new_default_package(db, application)
    elif package.sent_at is None and _is_untouched_empty_draft(package):
        await _apply_default_selection(db, application, package)
        await db.flush()
    await db.commit()
    await db.refresh(package)
    return package


async def get_scoped_package(db: AsyncSession, package_id: uuid.UUID, user: User) -> QuotePackage:
    """404 (Decision #11) unless the package's application is in scope."""
    stmt = scope_applications(
        select(Application.id)
        .join(QuotePackage, QuotePackage.application_id == Application.id)
        .where(QuotePackage.id == package_id),
        user,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise NotFoundError(f"Package not found: {package_id}")
    package = await db.get(QuotePackage, package_id)
    assert package is not None
    return package


async def _live_recommendation_text(db: AsyncSession, package: QuotePackage) -> str | None:
    """Re-drafts the sentence from the recommended quote's current
    rate/scenario for the response only (code review #1); quote ids survive
    a reprice, so an id check alone would leave "at 7.500%" after the rate
    moved.

    Read-only by design (code review M2): a GET used to persist this via
    `db.commit()` without holding `lock_application`, so a GET racing a PUT
    could overwrite the PUT's fresher text with a stale one. `GET
    /packages/{id}/report` already re-drafts on every read without
    persisting (`build_package_view_model` -> `current_recommendation_text`)
    -- the stored column is only a cache for `PackageRead`, refreshed for
    real on the next write (`update_package`, which does hold the lock)."""
    try:
        ctx = await load_package_context(db, package)
    except ValidationAppError:
        return package.recommendation_text
    fresh = current_recommendation_text(ctx, package.recommended_quote_id)
    return fresh if fresh is not None else package.recommendation_text


async def package_read(db: AsyncSession, package: QuotePackage) -> PackageRead:
    recommendation_text = await _live_recommendation_text(db, package)
    application = await db.get(Application, package.application_id)
    assert application is not None
    client_row = await db.get(Client, application.client_id)
    email = (client_row.email if client_row is not None else "") or ""
    return PackageRead(
        id=package.id,
        application_id=package.application_id,
        quote_ids=list(package.quote_ids or []),
        recommended_quote_id=package.recommended_quote_id,
        recommendation_text=recommendation_text,
        lo_note=package.lo_note,
        recipient_email=email.strip() or None,
        attachments=[LETTER_ATTACHMENT],
        sent_at=package.sent_at,
        updated_at=package.updated_at,
    )


async def update_package(
    db: AsyncSession, application: Application, body: PackageUpdate, user: User
) -> QuotePackage:
    """`PUT /applications/{id}/package`. Validates that every quote belongs
    to the application and the recommended quote is among them, re-drafts
    the recommendation text when the recommendation changes, and keeps
    `applications.recommended_quote_id` in step (plan.md Decision 8)."""
    application = await lock_application(db, application.id)
    quote_ids = list(body.quote_ids)
    if len(set(quote_ids)) != len(quote_ids):
        raise ValidationAppError("A quote can only be in the package once.")
    if len(quote_ids) > MAX_PACKAGE_QUOTES:
        raise ValidationAppError(f"A package holds at most {MAX_PACKAGE_QUOTES} quotes.")
    if quote_ids:
        owned = set(
            (
                await db.execute(
                    select(Quote.id)
                    .join(Scenario, Scenario.id == Quote.scenario_id)
                    .where(Scenario.application_id == application.id, Quote.id.in_(quote_ids))
                )
            )
            .scalars()
            .all()
        )
        if owned != set(quote_ids):
            raise ValidationAppError("Every quote must belong to this application.")
    recommended = body.recommended_quote_id
    if recommended is not None and recommended not in quote_ids:
        raise ValidationAppError("The recommended quote must be one of the selected quotes.")

    package = await _newest_package(db, application.id)
    if package is None:
        package = await new_default_package(db, application)

    if recommended != package.recommended_quote_id or package.recommendation_text is None:
        package.recommendation_text = await recommendation_text_for(db, application, recommended)
    package.quote_ids = quote_ids
    package.recommended_quote_id = recommended
    note = (body.lo_note or "").strip()
    package.lo_note = note or None
    # code-review follow-up on M5: a real PUT, even one that empties the
    # draft, must stick -- the next GET must not treat it as still
    # untouched and refill it.
    package.lo_edited = True

    if recommended is not None and application.recommended_quote_id != recommended:
        previous = application.recommended_quote_id
        application.recommended_quote_id = recommended
        db.add(
            ActivityEvent(
                application_id=application.id,
                actor=str(user.id),
                type="quote.recommended",
                payload={
                    "quote_id": str(recommended),
                    "previous_quote_id": str(previous) if previous is not None else None,
                    "source": "send_tab",
                },
                at=datetime.now(UTC),
            )
        )
    await db.flush()
    await db.commit()
    await db.refresh(package)
    return package


async def package_readiness(db: AsyncSession, package: QuotePackage) -> PackageReadiness:
    blockers = await package_blockers(db, package)
    return PackageReadiness(
        ready=not blockers,
        blockers=[ReadinessBlocker(code=b.code, message=b.message, tab=b.tab) for b in blockers],
    )


async def package_report(db: AsyncSession, package: QuotePackage) -> ReportViewModel:
    """The LO preview: exactly what `freeze_package_version` would snapshot
    if the package were sent today (AC2)."""
    today = datetime.now(UTC)
    return await build_package_view_model(
        db,
        package,
        recommendation_text=None,
        lo_note=None,
        as_of=today.date(),
        expires_at=(today + timedelta(days=PREVIEW_EXPIRY_DAYS)).date(),
    )
