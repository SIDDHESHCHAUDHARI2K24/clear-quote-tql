"""`build_package_view_model` -- the ONE function that turns a quote package
into the borrower's `ReportViewModel` (CQ-019 plan.md Decision 3).

The LO's Send-tab preview (`GET /packages/{id}/report`) calls it with the
live draft; `portal/reports/versions.py::freeze_package_version` calls it at
send time and stores the result as the version snapshot the portal serves.
Because both go through here, the preview and the sent report can only
differ in the send-time header fields (`prepared_at`, `rates_as_of`,
`expires_at`, `expired`, `superseded`) -- AC2's contract test pins that.

Maps `Quote`/`Scenario`/`Application`/`Property`/`Client`/`User` rows into
CQ-021's `ReportInputs`, adds CQ-023's matches, and runs CQ-021's pure
builder. Every dollar figure comes from `Quote.computed` (the engine's own
output); this module only labels and orders.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.core.errors import ValidationAppError
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
from app.features.quotes.report.schemas import ReportViewModel
from app.features.quotes.send.models import QuotePackage

DEFAULT_RECOMMENDATION_TEXT = "We recommend this option based on your loan file."
_DEFAULT_LO_TITLE = "Loan Officer"
DEFAULT_INVESTMENT_PPP_YEARS = 5
"""What the OB request sends for an investment scenario with no PPP set
(`pricing/scenarios/ob_request._DEFAULT_INVESTMENT_PPP_YEARS`), so the
report labels the prepay the quote was actually priced with (plan.md
Decision 15)."""


def strategy_type(application: Application) -> StrategyType:
    """Same mapping as `pricing/scenarios/service.py::_strategy_type`;
    raises the same clean 4xx for an investment application with no
    strategy."""
    if application.occupancy is Occupancy.PRIMARY:
        return StrategyType.PRIMARY
    if application.strategy is Strategy.LTR:
        return StrategyType.LTR
    if application.strategy is Strategy.STR:
        return StrategyType.STR
    raise ValidationAppError(f"Application {application.id} has no strategy set")


def ppp_years(strategy: StrategyType, scenario: Scenario) -> int | None:
    """`None` for primary (never shows a PPP); else the scenario's PPP
    years, defaulting to what it was priced with."""
    if strategy is StrategyType.PRIMARY:
        return None
    raw = scenario.inputs if isinstance(scenario.inputs, dict) else {}
    years = raw.get("prepayment_penalty_years")
    return DEFAULT_INVESTMENT_PPP_YEARS if years is None else int(years)


def prepay_label(strategy: StrategyType, scenario: Scenario) -> str:
    years = ppp_years(strategy, scenario)
    if years:
        return f"{years}-year prepayment penalty"
    return "No prepayment penalty"


def property_label(prop: Property | None) -> str | None:
    """`None` renders as "Property to be determined" (builder.py)."""
    if prop is None or prop.address_status is PropertyAddressStatus.TBD:
        return None
    city_state_zip = " ".join(p for p in (prop.state, prop.zip) if p)
    pieces = [p for p in (prop.street_address, prop.city, city_state_zip) if p]
    return ", ".join(pieces) if pieces else None


@dataclass(frozen=True)
class PackageContext:
    """Every row a package's report and letter read, loaded once."""

    application: Application
    client: Client
    lo: User
    prop: Property | None
    strategy: StrategyType
    quotes: list[Quote]
    """The package's quotes in `quote_ids` order (missing ids dropped)."""
    scenarios: dict[uuid.UUID, Scenario]


async def load_package_context(db: AsyncSession, package: QuotePackage) -> PackageContext:
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
    strategy = strategy_type(application)

    quote_ids = list(package.quote_ids or [])
    quotes_by_id = (
        {
            q.id: q
            for q in (await db.execute(select(Quote).where(Quote.id.in_(quote_ids)))).scalars()
        }
        if quote_ids
        else {}
    )
    ordered = [quotes_by_id[qid] for qid in quote_ids if qid in quotes_by_id]
    scenario_ids = {q.scenario_id for q in ordered}
    scenarios = (
        {
            s.id: s
            for s in (
                await db.execute(select(Scenario).where(Scenario.id.in_(scenario_ids)))
            ).scalars()
        }
        if scenario_ids
        else {}
    )
    return PackageContext(
        application=application,
        client=client_row,
        lo=lo,
        prop=prop,
        strategy=strategy,
        quotes=ordered,
        scenarios=scenarios,
    )


async def build_package_view_model(
    db: AsyncSession,
    package: QuotePackage,
    *,
    recommendation_text: str | None,
    lo_note: str | None,
    as_of: date,
    expires_at: date | None,
    expired: bool = False,
    superseded: bool = False,
) -> ReportViewModel:
    """The borrower report for `package` as of `as_of` (send date, or today
    for the LO preview). `recommendation_text`/`lo_note` fall back to the
    package's own stored values when `None`."""
    if not package.quote_ids:
        raise ValidationAppError("The package has no quotes to show.")
    ctx = await load_package_context(db, package)
    if not ctx.quotes:
        raise ValidationAppError("The package's quotes no longer exist.")

    first_inputs = ScenarioInputs.model_validate(ctx.scenarios[ctx.quotes[0].scenario_id].inputs)
    options: list[ReportOptionInput] = []
    for quote in ctx.quotes:
        scenario = ctx.scenarios[quote.scenario_id]
        options.append(
            ReportOptionInput(
                quote_id=str(quote.id),
                label=quote.label,
                recommended=quote.id == package.recommended_quote_id,
                note_rate=quote.rate,
                down_payment_pct=ScenarioInputs.model_validate(scenario.inputs).down_payment_pct,
                discount_points_pct=quote.points,
                prepay_label=prepay_label(ctx.strategy, scenario),
                computation=QuoteComputation.model_validate(quote.computed),
            )
        )

    # CQ-023 (D4): matches run through the recommended quote's numbers.
    recommended_quote = next((q for q in ctx.quotes if q.id == package.recommended_quote_id), None)
    matches = await compute_matches_for_package(
        db, application=ctx.application, recommended_quote=recommended_quote
    )

    lo = ctx.lo
    inputs = ReportInputs(
        first_name=ctx.client.full_name.split()[0],
        property_label=property_label(ctx.prop),
        purchase_price=first_inputs.purchase_price,
        strategy=ctx.strategy,
        prepared_at=as_of,
        rates_as_of=as_of,
        expires_at=expires_at,
        expired=expired,
        superseded=superseded,
        options=options,
        recommendation_text=(
            recommendation_text or package.recommendation_text or DEFAULT_RECOMMENDATION_TEXT
        ),
        lo_note=lo_note if lo_note is not None else package.lo_note,
        lo_name=lo.full_name,
        lo_title=lo.title or _DEFAULT_LO_TITLE,
        lo_nmls=lo.nmls or "",
        lo_phone=lo.phone or "",
        lo_email=lo.email,
        matches=matches,
    )
    return build_report_view_model(inputs)
