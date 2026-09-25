"""Builds the workspace summary (spec.md CQ-016) and applies the
Withdrawn/Closed status transition.

Header-number sourcing (plan.md decisions #3/#4/#5): "purchasing power",
down payment % and $, and PPP years all come from the application's
*current scenario* -- the scenario behind `recommended_quote_id`'s quote
when set, else the most-recently-created `Scenario`, else `None` when no
scenario exists yet. Down payment $ is `quote_engine.compute_quote`'s own
`down_payment_amount` field (AGENTS.md: "Money math lives only in
`quote_engine`") -- CQ-021 landed that field on `QuoteComputation` while
this item was in flight, so what started as a same-formula local copy
(logged in an earlier revision of this docstring/plan.md decision #4) now
calls the engine directly, with a same-formula fallback only for a
scenario the engine can't price yet (see `_scenario_numbers`). Note rate
is the recommended `Quote.rate` verbatim, never re-derived.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, ApplicationTab
from app.core.errors import ConflictError
from app.features.applications.models import Application
from app.features.applications.property.models import Property
from app.features.applications.summary.schemas import (
    ApplicationSummaryResponse,
    LocationResponse,
    StatusPatchRequest,
    TabStateResponse,
    TabStateValue,
)
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.features.clients.models import Client
from app.features.pricing.engine.quote_engine import LtvOutOfRangeError, compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote

_CENT = Decimal("0.01")

# spec.md "Application status machine": statuses reachable only once
# `draft_quote_set` has run at least once -- the default-tab rule's "status
# >= Priced" (plan.md decision #7).
_PRICED_OR_LATER = frozenset(
    {
        ApplicationStatus.PRICED,
        ApplicationStatus.SENT,
        ApplicationStatus.VIEWED,
        ApplicationStatus.OPTION_SELECTED,
        ApplicationStatus.INQUIRY,
        ApplicationStatus.STALE,
    }
)

_TERMINAL_APPLICATION_STATUSES = frozenset({ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED})

_STATUS_EVENT_TYPE: dict[ApplicationStatus, str] = {
    ApplicationStatus.WITHDRAWN: "application.withdrawn",
    ApplicationStatus.CLOSED: "application.closed",
}


@dataclass(frozen=True)
class _CurrentScenarioNumbers:
    purchasing_power: Decimal | None
    down_payment_pct: Decimal | None
    down_payment_amount: Decimal | None
    ppp_years: int | None


def _down_payment_amount_fallback(purchase_price: Decimal, down_payment_pct: Decimal) -> Decimal:
    """`purchase_price * down_payment_pct`, rounded half-up to cents -- the
    exact formula/rounding `quote_engine.compute_quote` uses for its own
    `down_payment_amount` field. Used only when `compute_quote` itself
    can't run for this scenario yet (`_scenario_numbers`'s `LtvOutOfRangeError`
    catch) -- down payment $ is well-defined independent of the LTV guard
    that blocks the rest of the engine's output."""
    return (purchase_price * down_payment_pct).quantize(_CENT, rounding=ROUND_HALF_UP)


async def _current_scenario(db: AsyncSession, application: Application) -> Scenario | None:
    if application.recommended_quote_id is not None:
        quote = await db.get(Quote, application.recommended_quote_id)
        if quote is not None:
            scenario = await db.get(Scenario, quote.scenario_id)
            if scenario is not None:
                return scenario
    stmt = (
        select(Scenario)
        .where(Scenario.application_id == application.id)
        .order_by(Scenario.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


def _down_payment_amount(scenario: Scenario, inputs: ScenarioInputs) -> Decimal:
    config = (
        ConfigSnapshot.model_validate(scenario.config_snapshot)
        if isinstance(scenario.config_snapshot, dict)
        else ConfigSnapshot()
    )
    try:
        return compute_quote(inputs, config).down_payment_amount
    except LtvOutOfRangeError:
        # A scenario that was created but never successfully priced (e.g.
        # its down payment % implies an LTV the engine rejects before any
        # quote exists for it) -- fall back to the same formula/rounding
        # rather than 500ing the whole summary over an unrelated field.
        return _down_payment_amount_fallback(inputs.purchase_price, inputs.down_payment_pct)


def _scenario_numbers(scenario: Scenario | None) -> _CurrentScenarioNumbers:
    if scenario is None or not isinstance(scenario.inputs, dict):
        return _CurrentScenarioNumbers(None, None, None, None)
    inputs = ScenarioInputs.model_validate(scenario.inputs)
    ppp_years = scenario.inputs.get("prepayment_penalty_years")
    return _CurrentScenarioNumbers(
        purchasing_power=inputs.purchase_price,
        down_payment_pct=inputs.down_payment_pct,
        down_payment_amount=_down_payment_amount(scenario, inputs),
        ppp_years=int(ppp_years) if ppp_years is not None else None,
    )


async def _note_rate(db: AsyncSession, application: Application) -> Decimal | None:
    if application.recommended_quote_id is None:
        return None
    quote = await db.get(Quote, application.recommended_quote_id)
    return quote.rate if quote is not None else None


def _tab_state(open_flag_count: int, status: ApplicationStatus) -> TabStateValue:
    """plan.md decision #6: `flagged` whenever a tab has an open flag,
    else `pending` while the pipeline hasn't started evaluating anything
    yet (`status == INTAKE`), else `ok`."""
    if open_flag_count > 0:
        return "flagged"
    if status is ApplicationStatus.INTAKE:
        return "pending"
    return "ok"


async def _tab_states(
    db: AsyncSession, application: Application
) -> tuple[list[TabStateResponse], ApplicationTab]:
    rows = (
        await db.execute(
            select(Flag.tab, Flag.id).where(
                Flag.application_id == application.id, Flag.resolved_at.is_(None)
            )
        )
    ).all()
    counts: dict[ApplicationTab, int] = {}
    for tab, _flag_id in rows:
        counts[tab] = counts.get(tab, 0) + 1

    tabs: list[TabStateResponse] = []
    first_flagged: ApplicationTab | None = None
    for tab in ApplicationTab:
        count = counts.get(tab, 0)
        state = _tab_state(count, application.status)
        if state == "flagged" and first_flagged is None:
            first_flagged = tab
        tabs.append(TabStateResponse(tab=tab, state=state, flag_count=count))

    if first_flagged is not None:
        default_tab = first_flagged
    elif application.status in _PRICED_OR_LATER:
        default_tab = ApplicationTab.PRICING
    else:
        default_tab = ApplicationTab.BORROWERS
    return tabs, default_tab


async def build_application_summary(
    db: AsyncSession, application: Application
) -> ApplicationSummaryResponse:
    client = await db.get(Client, application.client_id)
    client_name = client.full_name if client is not None else "Unknown client"

    property_row = (
        await db.execute(select(Property).where(Property.application_id == application.id))
    ).scalar_one_or_none()
    location = (
        LocationResponse(city=property_row.city, state=property_row.state, zip=property_row.zip)
        if property_row is not None
        else None
    )

    scenario = await _current_scenario(db, application)
    numbers = _scenario_numbers(scenario)
    note_rate = await _note_rate(db, application)
    tabs, default_tab = await _tab_states(db, application)

    return ApplicationSummaryResponse(
        application_id=application.id,
        client_name=client_name,
        status=application.status,
        last_pipeline_stage=application.last_pipeline_stage,
        occupancy=application.occupancy,
        strategy=application.strategy,
        program=application.program,
        location=location,
        purchasing_power=numbers.purchasing_power,
        down_payment_pct=numbers.down_payment_pct,
        down_payment_amount=numbers.down_payment_amount,
        ppp_years=numbers.ppp_years,
        note_rate=note_rate,
        tabs=tabs,
        default_tab=default_tab,
    )


async def patch_application_status(
    db: AsyncSession,
    application: Application,
    request: StatusPatchRequest,
    actor_id: uuid.UUID,
) -> ApplicationSummaryResponse:
    """spec.md AC6: sets `status`, writes one `activity_events` row with the
    reason, and hides the actions menu (client-side, once `status` is
    terminal). 409s if the application is already `withdrawn`/`closed`
    (plan.md decision #8 -- "from any non-terminal status").

    `SELECT ... FOR UPDATE` (with `populate_existing` so the in-memory
    `application.status` reflects whatever this locked, committed row
    actually holds, not a possibly-stale value from the `get_scoped_
    application` dependency's earlier read) closes a race: two concurrent
    PATCHes for the same application would otherwise both pass the
    terminal-status check and both commit, instead of the second one
    409ing as "from any non-terminal status" intends.
    """
    application = (
        await db.execute(
            select(Application)
            .where(Application.id == application.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    if application.status in _TERMINAL_APPLICATION_STATUSES:
        raise ConflictError(f"Application {application.id} is already {application.status.value}.")

    application.status = request.status
    db.add(
        ActivityEvent(
            application_id=application.id,
            actor=str(actor_id),
            type=_STATUS_EVENT_TYPE[request.status],
            payload={"reason": request.reason},
            at=datetime.now(UTC),
        )
    )
    await db.commit()
    await db.refresh(application)
    return await build_application_summary(db, application)
