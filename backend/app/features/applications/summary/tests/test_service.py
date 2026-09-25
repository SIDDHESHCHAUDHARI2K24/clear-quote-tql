"""spec.md AC1-AC4, AC6: `build_application_summary`'s header numbers, tab
states/default tab, and `patch_application_status`'s terminal-only
transition + activity event.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import Mock

import pytest
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.features.applications.summary.service as summary_service
from app.core.enums import ApplicationStatus, ApplicationTab
from app.core.errors import ConflictError
from app.features.applications.models import Application
from app.features.applications.property.models import Property
from app.features.applications.summary.schemas import StatusPatchRequest
from app.features.applications.summary.service import (
    build_application_summary,
    patch_application_status,
)
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.features.pricing.engine.quote_engine import compute_quote as real_compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote

# PR review round 1, MAJOR 1: covers a primary loan, an LTR investment, an
# STR investment, a needs_attention persona (no scenario ever created) and
# a sent persona -- via the real seed loader (the same Import -> Verify ->
# Enrich -> Validate -> AutoQuote -> DraftQuoteSet chain `make demo-reset`
# and the real Temporal pipeline both run), not a hand-built `make_scenario`
# fixture.
_AC1_PERSONA_KEYS = [
    "priya_nair",  # primary
    "kathleen_mcreynolds",  # LTR
    "marcus_hale",  # STR
    "aisha_coleman",  # needs_attention -- pricing never runs, no scenario
    "grace_kim",  # sent
]


async def test_summary_purchasing_power_and_down_payment_on_a_hand_built_scenario(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
) -> None:
    """Narrow unit case on top of `test_summary_matches_engine` (the real
    AC1 test, below, run against real seeded personas): purchasing power /
    down payment % come straight from the current scenario's `ScenarioInputs`;
    down payment $ matches `purchase_price * down_payment_pct` rounded
    half-up to cents -- the same value `quote_engine.compute_quote` itself
    returns for these inputs (proven end to end by `test_summary_matches_
    engine`, not re-derived here)."""
    application = await make_application()
    purchase_price = Decimal("342000.00")
    down_payment_pct = Decimal("0.25")
    await make_scenario(
        application, purchase_price=purchase_price, down_payment_pct=down_payment_pct
    )

    summary = await build_application_summary(db_session, application)

    expected_down_payment = (purchase_price * down_payment_pct).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert summary.purchasing_power == purchase_price
    assert summary.down_payment_pct == down_payment_pct
    assert summary.down_payment_amount == expected_down_payment


@pytest.mark.parametrize("persona_key", _AC1_PERSONA_KEYS)
async def test_summary_matches_engine(
    db_session: AsyncSession,
    persona_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1 (PR review round 1, MAJOR 1): every header number the summary
    returns equals what `quote_engine.compute_quote` itself gives for the
    persona's current scenario -- computed by CALLING the engine (not
    re-deriving its formulas) against the exact `ScenarioInputs`/
    `ConfigSnapshot` the real seed pipeline persisted. Also asserts the
    service actually calls the engine (a spy wrapping the real function),
    rather than a copy that happens to agree today."""
    spy = Mock(wraps=real_compute_quote)
    monkeypatch.setattr(summary_service, "compute_quote", spy)

    user_result = await seed_users(db_session)
    await seed_providers(db_session)
    personas = {p["key"]: p for p in load_persona_fixtures()}
    persona = personas[persona_key]

    seed_result = await seed_persona(
        db_session, persona, lo_id=user_result.lo_ids[0], s3_client=None
    )
    application = await db_session.get(Application, seed_result.application_id)
    assert application is not None

    summary = await build_application_summary(db_session, application)

    assert summary.program == application.program
    assert summary.strategy == application.strategy
    assert summary.location is not None
    assert summary.location.city == persona["market"]["city"]
    assert summary.location.state == persona["market"]["state"]
    assert summary.location.zip == persona["market"]["zip"]

    scenario = (
        (
            await db_session.execute(
                select(Scenario)
                .where(Scenario.application_id == application.id)
                .order_by(Scenario.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if scenario is None:
        # e.g. Aisha Coleman: pricing never ran (missing-occupancy defect),
        # so there is no scenario -- header numbers must be null and the
        # engine is never called for this persona.
        assert summary.purchasing_power is None
        assert summary.down_payment_pct is None
        assert summary.down_payment_amount is None
        assert not spy.called
        return

    assert isinstance(scenario.inputs, dict)
    inputs = ScenarioInputs.model_validate(scenario.inputs)
    config = ConfigSnapshot.model_validate(scenario.config_snapshot)
    expected = real_compute_quote(inputs, config)

    assert summary.purchasing_power == inputs.purchase_price
    assert summary.down_payment_pct == inputs.down_payment_pct
    assert summary.down_payment_amount == expected.down_payment_amount
    assert summary.ppp_years == scenario.inputs.get("prepayment_penalty_years")
    assert spy.called


async def test_down_payment_amount_is_null_when_engine_rejects_the_ltv(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
) -> None:
    """PR review round 1, MAJOR 2: down payment $ comes from `quote_engine.
    compute_quote` (AGENTS.md: money math lives only in `quote_engine`), with
    no local fallback formula. A scenario that was created and never
    successfully priced can carry a down payment % the engine's own LTV
    guard rejects (`LtvOutOfRangeError`) -- the summary returns `null`
    (never 500s), and the UI renders "—" for it like any other null header
    number."""
    application = await make_application()
    await make_scenario(
        application,
        purchase_price=Decimal("300000.00"),
        down_payment_pct=Decimal("0.01"),  # 99% LTV -- over the engine's 97% cap
    )

    summary = await build_application_summary(db_session, application)

    assert summary.down_payment_amount is None
    # Purchasing power / down payment % are still well-defined -- only the
    # engine-derived $ amount degrades.
    assert summary.purchasing_power == Decimal("300000.00")
    assert summary.down_payment_pct == Decimal("0.01")


async def test_scenario_numbers_degrade_to_null_on_malformed_scenario_inputs(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
) -> None:
    """PR review round 1 (minor): a scenario whose `inputs` JSON doesn't
    validate as `ScenarioInputs` (corrupted row, schema drift, ...) must
    degrade the summary's header numbers to null instead of 500ing the
    whole endpoint."""
    application = await make_application()
    scenario = await make_scenario(application)
    scenario.inputs = {"purchase_price": "not-a-decimal", "this_is": "malformed"}
    await db_session.flush()

    summary = await build_application_summary(db_session, application)

    assert summary.purchasing_power is None
    assert summary.down_payment_pct is None
    assert summary.down_payment_amount is None
    assert summary.ppp_years is None


async def test_summary_no_scenario_yet_numbers_are_null(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application()

    summary = await build_application_summary(db_session, application)

    assert summary.purchasing_power is None
    assert summary.down_payment_pct is None
    assert summary.down_payment_amount is None
    assert summary.note_rate is None


async def test_primary_scenario_has_no_ppp(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
) -> None:
    """AC2: a primary scenario carries no PPP years."""
    application = await make_application()
    await make_scenario(application, strategy=StrategyType.PRIMARY, ppp_years=None)

    summary = await build_application_summary(db_session, application)

    assert summary.ppp_years is None


async def test_investment_scenario_reports_ppp_years(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
) -> None:
    """AC2: an STR/LTR scenario's PPP years pass through."""
    application = await make_application()
    await make_scenario(application, strategy=StrategyType.STR, ppp_years=5)

    summary = await build_application_summary(db_session, application)

    assert summary.ppp_years == 5


async def test_note_rate_null_without_recommended_quote(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
    make_quote: Callable[..., Awaitable[Quote]],
) -> None:
    """AC3: note rate is null when no quote is recommended, even if quotes
    exist."""
    application = await make_application()
    scenario = await make_scenario(application)
    await make_quote(scenario, rate=Decimal("7.125"))

    summary = await build_application_summary(db_session, application)

    assert summary.note_rate is None


async def test_note_rate_is_the_recommended_quotes_rate(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_scenario: Callable[..., Awaitable[Scenario]],
    make_quote: Callable[..., Awaitable[Quote]],
) -> None:
    """AC3: 7.500% once a quote is marked recommended."""
    application = await make_application()
    scenario = await make_scenario(application)
    quote = await make_quote(scenario, rate=Decimal("7.500"))
    application.recommended_quote_id = quote.id
    await db_session.flush()

    summary = await build_application_summary(db_session, application)

    assert summary.note_rate == Decimal("7.500")


async def test_location_from_property(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_property: Callable[..., Awaitable[Property]],
) -> None:
    application = await make_application()
    await make_property(application, city="Tampa", state="FL", zip_code="33602")

    summary = await build_application_summary(db_session, application)

    assert summary.location is not None
    assert (summary.location.city, summary.location.state, summary.location.zip) == (
        "Tampa",
        "FL",
        "33602",
    )


async def test_location_null_without_property(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application()

    summary = await build_application_summary(db_session, application)

    assert summary.location is None


async def test_tab_states_flags(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_flag: Callable[..., Awaitable[Flag]],
) -> None:
    """AC4 (Ben Ford shape): an open Housing flag shows `flagged` with the
    right count; an application past INTAKE with no flags on a tab shows
    `ok`."""
    application = await make_application(status=ApplicationStatus.NEEDS_ATTENTION)
    await make_flag(application, ApplicationTab.HOUSING)
    await make_flag(application, ApplicationTab.HOUSING)
    await make_flag(application, ApplicationTab.BORROWERS, resolved=True)  # resolved -> not counted

    summary = await build_application_summary(db_session, application)

    by_tab = {row.tab: row for row in summary.tabs}
    assert by_tab[ApplicationTab.HOUSING].state == "flagged"
    assert by_tab[ApplicationTab.HOUSING].flag_count == 2
    assert by_tab[ApplicationTab.BORROWERS].state == "ok"
    assert by_tab[ApplicationTab.BORROWERS].flag_count == 0
    assert summary.default_tab == ApplicationTab.HOUSING


async def test_tab_states_pending_at_intake(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(status=ApplicationStatus.INTAKE)

    summary = await build_application_summary(db_session, application)

    assert all(row.state == "pending" for row in summary.tabs)
    assert summary.default_tab == ApplicationTab.BORROWERS


async def test_default_tab_is_pricing_when_priced_and_unflagged(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(status=ApplicationStatus.PRICED)

    summary = await build_application_summary(db_session, application)

    assert summary.default_tab == ApplicationTab.PRICING


async def test_default_tab_first_flagged_wins_over_pricing(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_flag: Callable[..., Awaitable[Flag]],
) -> None:
    application = await make_application(status=ApplicationStatus.PRICED)
    await make_flag(application, ApplicationTab.CREDIT)

    summary = await build_application_summary(db_session, application)

    assert summary.default_tab == ApplicationTab.CREDIT


async def test_status_patch_withdraws_and_writes_activity_event(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(status=ApplicationStatus.PRICED)
    actor_id = application.lo_id

    summary = await patch_application_status(
        db_session,
        application,
        StatusPatchRequest(status=ApplicationStatus.WITHDRAWN, reason="Borrower backed out"),
        actor_id,
    )

    assert summary.status == ApplicationStatus.WITHDRAWN
    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(ActivityEvent.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].type == "application.withdrawn"
    assert events[0].payload == {"reason": "Borrower backed out"}


async def test_status_patch_already_terminal_conflicts(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application(status=ApplicationStatus.WITHDRAWN)

    with pytest.raises(ConflictError):
        await patch_application_status(
            db_session,
            application,
            StatusPatchRequest(status=ApplicationStatus.CLOSED),
            uuid.uuid4(),
        )
