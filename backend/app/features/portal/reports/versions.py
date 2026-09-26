"""`freeze_package_version` -- the sent-version factory (D2,
docs/backlog/phase-p3-p4-foundation.md; CQ-022 plan.md Decision 2).

Freezes a `QuotePackage`'s currently-drafted quotes into a new, immutable
`QuotePackageVersion` row: maps `Quote`/`Scenario`/`Application`/`Property`/
`Client`/`User` rows into CQ-021's `ReportInputs`, runs them through the pure
`build_report_view_model`, and persists the resulting `ReportViewModel` JSON
as the version's `snapshot`. CQ-020's send workflow will call this for a real
send; until then, this item's own `seed/loader.py::apply_send_fixture` and
its tests call it directly (spec.md "Notes for the agent": "This item can
run before CQ-020").

Every dollar figure here traces to `Quote.computed` (the engine's own JSON
output, written by `pricing/scenarios/service.py::_persist_quote`) -- this
module reads already-priced rows and formats/labels them; it performs no
pricing math of its own.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.security import generate_token
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from app.features.quotes.send.view_model import build_package_view_model

REPORT_EXPIRY_DAYS = 21
"""H2 (docs/backlog/phase-p3-p4-plan.md): "The report expires 21 days after
send" -- distinct from `quote_packages.expires_at` (the draft package's own,
unrelated 7-day field, left alone here per D2)."""


async def freeze_package_version(
    db: AsyncSession,
    *,
    package: QuotePackage,
    recommendation_text: str | None = None,
    lo_note: str | None = None,
    letter_key: str | None = None,
    sent_at: datetime | None = None,
) -> QuotePackageVersion:
    """Freezes `package`'s current `quote_ids`/`recommended_quote_id` into a
    new `QuotePackageVersion` row and flips every prior non-superseded
    version of the same package to `superseded=True`. Flushes but does not
    commit -- the caller (a request handler, a Temporal activity, or a
    seed/test helper) controls the transaction boundary.

    CQ-019: the snapshot comes from `build_package_view_model`, the same
    function the LO's Send-tab preview calls, so the sent report is exactly
    the previewed one (AC2). `recommendation_text`/`lo_note` default to the
    package's stored values.
    """
    # Fresh-subagent review finding (fixed): two concurrent freezes of the
    # same package race on `max(version)`; `SELECT ... FOR UPDATE` on the
    # package row serializes freezes of the *same* package.
    await db.execute(select(QuotePackage.id).where(QuotePackage.id == package.id).with_for_update())

    if not package.quote_ids:
        raise ValueError(f"QuotePackage {package.id} has no quotes to freeze")

    resolved_sent_at = sent_at or clock.now()
    expires_at = resolved_sent_at + timedelta(days=REPORT_EXPIRY_DAYS)

    view_model = await build_package_view_model(
        db,
        package,
        recommendation_text=recommendation_text,
        lo_note=lo_note,
        as_of=resolved_sent_at.date(),
        expires_at=expires_at.date(),
    )

    next_version_number = (
        await db.execute(
            select(func.coalesce(func.max(QuotePackageVersion.version), 0)).where(
                QuotePackageVersion.package_id == package.id
            )
        )
    ).scalar_one()

    await db.execute(
        update(QuotePackageVersion)
        .where(
            QuotePackageVersion.package_id == package.id,
            QuotePackageVersion.superseded.is_(False),
        )
        .values(superseded=True)
    )

    version = QuotePackageVersion(
        package_id=package.id,
        version=next_version_number + 1,
        snapshot=view_model.model_dump(mode="json"),
        letter_key=letter_key,
        report_token=generate_token(),
        sent_at=resolved_sent_at,
        expires_at=expires_at,
        viewed_at=None,
        superseded=False,
        borrower_action=None,
    )
    db.add(version)
    await db.flush()
    return version
