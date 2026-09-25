"""Quote package draft service (CQ-019).

One working package per application (D2; plan.md Decision 2): the newest
`quote_packages` row. The first `GET` creates the default draft under the
application's write lock, so two concurrent first loads never create two.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
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
from app.features.quotes.send.view_model import build_package_view_model, strategy_type

PREVIEW_EXPIRY_DAYS = 21
"""Same as `portal/reports/versions.REPORT_EXPIRY_DAYS`: the preview shows
the expiry the borrower would see if the LO sent now."""

LETTER_ATTACHMENT = "Pre-approval letter (PDF)"


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


async def new_default_package(db: AsyncSession, application: Application) -> QuotePackage:
    """Builds (and flushes) the default draft; the caller commits. Also used
    by the seed's `apply_send_fixture`, so seeded packages follow the same
    rule."""
    selection = await default_package_selection(db, application)
    package = QuotePackage(
        application_id=application.id,
        quote_ids=selection.quote_ids,
        recommended_quote_id=selection.recommended_quote_id,
        recommendation_text=await recommendation_text_for(
            db, application, selection.recommended_quote_id
        ),
        report_token=secrets.token_urlsafe(24),
    )
    db.add(package)
    await db.flush()
    return package


async def get_or_create_package(db: AsyncSession, application: Application) -> QuotePackage:
    package = await _newest_package(db, application.id)
    if package is not None:
        return package
    await lock_application(db, application.id)
    package = await _newest_package(db, application.id)
    if package is None:
        package = await new_default_package(db, application)
    await db.commit()
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


async def package_read(db: AsyncSession, package: QuotePackage) -> PackageRead:
    application = await db.get(Application, package.application_id)
    assert application is not None
    client_row = await db.get(Client, application.client_id)
    email = (client_row.email if client_row is not None else "") or ""
    return PackageRead(
        id=package.id,
        application_id=package.application_id,
        quote_ids=list(package.quote_ids or []),
        recommended_quote_id=package.recommended_quote_id,
        recommendation_text=package.recommendation_text,
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
