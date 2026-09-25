"""Persona 7 and 8 (docs/backlog/CQ-010-seed-data/spec.md persona table) —
AC1's roadmap exit check. CQ-010's seed doesn't exist yet, so these use
literal fixtures matching the persona table's raw inputs directly.
"""

from collections.abc import Awaitable, Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy, Strategy
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.verification.models import Flag
from app.features.applications.verification.service import run_and_persist, write_flag


async def test_persona_8_housing_flag(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """Ben Ford — Primary, Fort Wayne IN, 14 months at current address, no
    prior address on file. `housing_history_24mo` fails end to end through
    `run_and_persist` (a CQ-012 rule, tested directly, per spec.md)."""
    application = await make_application(
        occupancy=Occupancy.PRIMARY,
        requested_price=260_000,
        subject_state="IN",
    )
    db_session.add(
        ApplicationParty(
            application_id=application.id,
            role=PartyRole.BORROWER,
            first_name="Ben",
            last_name="Ford",
            cell_phone="2605551234",
            ssn_encrypted="123456789",
            dob=date(1988, 3, 4),
        )
    )
    db_session.add(
        HousingHistory(
            application_id=application.id,
            sequence=0,
            street_address="118 W Main St",
            city="Fort Wayne",
            state="IN",
            zip="46802",
            housing_status=HousingStatus.RENT,
            residence_years=1,
            residence_months=2,  # 14 months total, no prior row
        )
    )
    await db_session.flush()

    results = await run_and_persist(application.id, db_session)

    housing_result = next(r for r in results if r.rule_id == "housing_history_24mo")
    assert housing_result.passed is False

    flag = (
        await db_session.execute(
            select(Flag).where(
                Flag.application_id == application.id, Flag.rule == "housing_history_24mo"
            )
        )
    ).scalar_one()
    assert flag.tab is ApplicationTab.HOUSING
    assert flag.field_key == "current_residence_years"
    assert flag.severity is FlagSeverity.BLOCKING
    assert flag.resolved_at is None


async def test_persona_7_write_flag(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """Aisha Coleman — Investment/LTR, Columbus OH, `occupancy_type` null in
    the LOS record. Not a CQ-012 rule (system-design's exact wording: "Cannot
    price: missing Occupancy" is raised by CQ-013's pricing/enrichment
    service catching CQ-009's `PricingValidationError`) — this only proves
    `write_flag` behaves correctly when called with the same parameters that
    stage will use."""
    application = await make_application(occupancy=Occupancy.INVESTMENT, strategy=Strategy.LTR)

    flag = await write_flag(
        db_session,
        application.id,
        ApplicationTab.PRICING,
        "occupancy_type",
        "ob_required_field",
        FlagSeverity.BLOCKING,
    )

    assert flag.application_id == application.id
    assert flag.tab is ApplicationTab.PRICING
    assert flag.field_key == "occupancy_type"
    assert flag.rule == "ob_required_field"
    assert flag.severity is FlagSeverity.BLOCKING
    assert flag.resolved_at is None

    persisted = (
        await db_session.execute(select(Flag).where(Flag.application_id == application.id))
    ).scalar_one()
    assert persisted.id == flag.id
