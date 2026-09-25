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

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.core.errors import ValidationAppError
from app.core.security import generate_token
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.matches.service import compute_matches_for_package
from app.features.pricing.engine.types import QuoteComputation, ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.report.builder import build_report_view_model
from app.features.quotes.report.inputs import ReportInputs, ReportOptionInput
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion

REPORT_EXPIRY_DAYS = 21
"""H2 (docs/backlog/phase-p3-p4-plan.md): "The report expires 21 days after
send" -- distinct from `quote_packages.expires_at` (the draft package's own,
unrelated 7-day field, left alone here per D2)."""

_DEFAULT_RECOMMENDATION_TEXT = "We recommend this option based on your loan file."
_DEFAULT_LO_TITLE = "Loan Officer"


def _strategy_type(application: Application) -> StrategyType:
    """Same mapping as `pricing/scenarios/service.py::_strategy_type`
    (private to that module) -- duplicated here as a small, feature-local
    helper rather than importing another feature's underscore-prefixed
    symbol. Raises the same `ValidationAppError` (a clean 4xx) that module
    raises, not a bare `ValueError` (fresh-subagent review finding: the two
    copies had diverged into different failure modes for the identical
    "investment application, no strategy set" case -- a clean validation
    error at pricing time vs. an unhandled 500 at freeze time)."""
    if application.occupancy is Occupancy.PRIMARY:
        return StrategyType.PRIMARY
    if application.strategy is Strategy.LTR:
        return StrategyType.LTR
    if application.strategy is Strategy.STR:
        return StrategyType.STR
    raise ValidationAppError(f"Application {application.id} has no strategy set")


def _prepay_label(strategy: StrategyType, ppp_years: int | None) -> str:
    """ "5-year prepayment penalty" / "No prepayment penalty" -- matches
    `backend/scripts/build_report_fixtures.py`'s own wording. Primary loans
    never carry a PPP (system-design.md)."""
    if strategy is StrategyType.PRIMARY:
        return "No prepayment penalty"
    if ppp_years:
        return f"{ppp_years}-year prepayment penalty"
    return "No prepayment penalty"


def _property_label(prop: Property | None) -> str | None:
    """`None` renders as "Property to be determined" (builder.py)."""
    if prop is None or prop.address_status is PropertyAddressStatus.TBD:
        return None
    city_state_zip = " ".join(p for p in (prop.state, prop.zip) if p)
    pieces = [p for p in (prop.street_address, prop.city, city_state_zip) if p]
    return ", ".join(pieces) if pieces else None


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
    """
    # Fresh-subagent review finding (fixed): two concurrent freezes of the
    # same package (a retried send activity overlapping the original, a
    # double-clicked send) previously raced on reading `max(version)` and
    # superseding prior rows -- both could compute the same "next version"
    # (one then fails the `(package_id, version)` unique constraint) or, on
    # a different interleaving, both new rows could end up non-superseded,
    # breaking the "at most one live version" invariant `SupersededBanner`/
    # `_newest_report_token_for_package` rely on. `SELECT ... FOR UPDATE` on
    # the package row serializes freezes of the *same* package (a second
    # transaction blocks here until the first commits and sees its fully
    # up-to-date version history); freezes of different packages never
    # contend since each locks only its own row.
    await db.execute(select(QuotePackage.id).where(QuotePackage.id == package.id).with_for_update())

    application = await db.get(Application, package.application_id)
    if application is None:
        raise ValueError(f"Application not found: {package.application_id}")

    client_row = await db.get(Client, application.client_id)
    if client_row is None:
        raise ValueError(f"Client not found: {application.client_id}")

    lo = await db.get(User, application.lo_id)
    if lo is None:
        raise ValueError(f"LO not found: {application.lo_id}")

    prop = (
        await db.execute(select(Property).where(Property.application_id == application.id))
    ).scalar_one_or_none()

    strategy = _strategy_type(application)

    if not package.quote_ids:
        raise ValueError(f"QuotePackage {package.id} has no quotes to freeze")

    quotes_by_id = {
        q.id: q
        for q in (await db.execute(select(Quote).where(Quote.id.in_(package.quote_ids))))
        .scalars()
        .all()
    }
    ordered_quotes = [quotes_by_id[qid] for qid in package.quote_ids if qid in quotes_by_id]
    if not ordered_quotes:
        raise ValueError(f"QuotePackage {package.id}'s quote_ids do not resolve to any Quote row")

    scenario_ids = {q.scenario_id for q in ordered_quotes}
    scenario_rows = (
        (await db.execute(select(Scenario).where(Scenario.id.in_(scenario_ids)))).scalars().all()
    )
    scenarios_by_id = {s.id: s for s in scenario_rows}

    first_scenario_inputs = ScenarioInputs.model_validate(
        scenarios_by_id[ordered_quotes[0].scenario_id].inputs
    )

    options: list[ReportOptionInput] = []
    for quote in ordered_quotes:
        scenario = scenarios_by_id[quote.scenario_id]
        scenario_inputs = ScenarioInputs.model_validate(scenario.inputs)
        raw_inputs = scenario.inputs if isinstance(scenario.inputs, dict) else {}
        ppp_years = raw_inputs.get("prepayment_penalty_years")
        computation = QuoteComputation.model_validate(quote.computed)
        options.append(
            ReportOptionInput(
                quote_id=str(quote.id),
                label=quote.label,
                recommended=quote.id == package.recommended_quote_id,
                note_rate=quote.rate,
                down_payment_pct=scenario_inputs.down_payment_pct,
                discount_points_pct=quote.points,
                prepay_label=_prepay_label(strategy, ppp_years),
                computation=computation,
            )
        )

    resolved_sent_at = sent_at or datetime.now(UTC)
    expires_at = resolved_sent_at + timedelta(days=REPORT_EXPIRY_DAYS)

    # CQ-023 (plan.md Decision 6 / phase-p3-p4-plan.md D4): matches are
    # computed from the same recommended quote being frozen into this
    # version, so they're frozen with it too (spec.md AC7) -- a later
    # `make demo-reset` or listing change never changes an already-sent
    # report.
    recommended_quote = (
        quotes_by_id.get(package.recommended_quote_id)
        if package.recommended_quote_id is not None
        else None
    )
    matches = await compute_matches_for_package(
        db, application=application, recommended_quote=recommended_quote
    )

    inputs = ReportInputs(
        first_name=client_row.full_name.split()[0],
        property_label=_property_label(prop),
        purchase_price=first_scenario_inputs.purchase_price,
        strategy=strategy,
        prepared_at=resolved_sent_at.date(),
        rates_as_of=resolved_sent_at.date(),
        expires_at=expires_at.date(),
        expired=False,
        superseded=False,
        options=options,
        recommendation_text=recommendation_text or _DEFAULT_RECOMMENDATION_TEXT,
        lo_note=lo_note if lo_note is not None else package.lo_note,
        lo_name=lo.full_name,
        lo_title=lo.title or _DEFAULT_LO_TITLE,
        lo_nmls=lo.nmls or "",
        lo_phone=lo.phone or "",
        lo_email=lo.email,
        matches=matches,
    )

    view_model = build_report_view_model(inputs)

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
