"""`GET /api/v1/portal/reports/{token}` (CQ-022 spec.md): resolves a sent
version by its report token, enforces the signed-in borrower owns the
underlying client (404 otherwise, never 403 -- Decision #11's style), and
records the first-view transition race-safely.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.auth import ensure_borrower_owns_client
from app.core.enums import ApplicationStatus
from app.core.errors import NotFoundError
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import BorrowerAccount
from app.features.quotes.report.schemas import ReportViewModel
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion

from .schemas import PortalReportResponse

_ACTOR_SYSTEM = "system"
_EVENT_VIEWED = "quote.viewed"


async def _mark_viewed_if_first_load(
    db: AsyncSession, *, version: QuotePackageVersion, application: Application, now: datetime
) -> None:
    """Conditional `UPDATE ... WHERE viewed_at IS NULL` (CQ-022 plan.md
    Decision 9): only the request whose update actually affects a row --
    i.e. the first successful load -- writes the status transition and the
    activity event. Under Postgres's default READ COMMITTED isolation, a
    concurrent second request's `UPDATE` blocks on the row lock and then
    re-evaluates the `WHERE` after the first commits, finding `viewed_at` no
    longer `NULL`, so it affects 0 rows -- no double event."""
    result = cast(
        CursorResult,
        await db.execute(
            update(QuotePackageVersion)
            .where(QuotePackageVersion.id == version.id, QuotePackageVersion.viewed_at.is_(None))
            .values(viewed_at=now)
        ),
    )
    if result.rowcount != 1:
        return

    if application.status is ApplicationStatus.SENT:
        # CQ-030 review: conditional, so a concurrent stale job that already
        # committed SENT -> STALE is never overwritten with VIEWED.
        await db.execute(
            update(Application)
            .where(
                Application.id == application.id,
                Application.status == ApplicationStatus.SENT,
            )
            .values(status=ApplicationStatus.VIEWED)
            .execution_options(synchronize_session="fetch")
        )

    db.add(
        ActivityEvent(
            application_id=application.id,
            actor=_ACTOR_SYSTEM,
            type=_EVENT_VIEWED,
            payload={"report_token": version.report_token, "version": version.version},
            at=now,
        )
    )
    await db.commit()


async def _newest_report_token_for_package(
    db: AsyncSession, *, package_id: uuid.UUID
) -> str | None:
    newest = (
        await db.execute(
            select(QuotePackageVersion)
            .where(
                QuotePackageVersion.package_id == package_id,
                QuotePackageVersion.superseded.is_(False),
            )
            .order_by(QuotePackageVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return newest.report_token if newest is not None else None


async def get_report_for_token(
    db: AsyncSession, *, token: str, borrower: BorrowerAccount
) -> PortalReportResponse:
    version = (
        await db.execute(
            select(QuotePackageVersion).where(QuotePackageVersion.report_token == token)
        )
    ).scalar_one_or_none()
    if version is None:
        raise NotFoundError("Report not found")

    package = await db.get(QuotePackage, version.package_id)
    if package is None:
        raise NotFoundError("Report not found")

    application = await db.get(Application, package.application_id)
    if application is None:
        raise NotFoundError("Report not found")

    # 404 (never 403) for a token belonging to another borrower's package
    # (spec.md AC5) -- ensure_borrower_owns_client already raises
    # NotFoundError, but with the message "Not found" (core/auth.py's own
    # generic wording), which let a caller tell a missing token ("Report not
    # found", above) apart from a foreign one. CQ-024 review carry-over
    # (fresh-subagent finding #1): re-raise with the identical message so
    # both cases are indistinguishable from the response alone.
    try:
        ensure_borrower_owns_client(borrower, application.client_id)
    except NotFoundError:
        raise NotFoundError("Report not found") from None

    # CQ-030: `core/clock.now()` (honours `CLOCK_NOW`, E2) so a demo with a
    # frozen clock shows the same `expired` state the stale job computed.
    now = clock.now()
    # `_mark_viewed_if_first_load` only ever writes `viewed_at`, which
    # nothing below reads -- no `db.refresh()` needed (fresh-subagent
    # review finding: it was a spurious extra SELECT on this hot path;
    # `snapshot`/`expires_at`/`superseded` are read from the row already
    # loaded above, and `expire_on_commit=False`, core/db.py, means that
    # commit doesn't expire them either).
    await _mark_viewed_if_first_load(db, version=version, application=application, now=now)

    view_model = ReportViewModel.model_validate(version.snapshot)
    expired = now > version.expires_at
    header = view_model.header.model_copy(
        update={"expired": expired, "superseded": version.superseded}
    )
    view_model = view_model.model_copy(update={"header": header})

    newest_report_token = None
    if version.superseded:
        newest_report_token = await _newest_report_token_for_package(db, package_id=package.id)

    borrower_action = version.borrower_action
    assert borrower_action is None or isinstance(borrower_action, dict)

    return PortalReportResponse(
        **view_model.model_dump(),
        borrower_action=borrower_action,
        newest_report_token=newest_report_token,
    )
