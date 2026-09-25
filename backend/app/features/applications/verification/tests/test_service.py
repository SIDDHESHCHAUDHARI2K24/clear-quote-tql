"""Integration tests for `service.py` against the real (test) database.

Covers AC3 (auto-fix rules never raise a `flags` row) and AC6 (`write_flag`
upserts on `(application_id, field_key, rule)`).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.verification.models import Flag
from app.features.applications.verification.service import run_and_persist, write_flag


async def _add_current_residence(
    db_session: AsyncSession, application_id: uuid.UUID, *, months: int
) -> None:
    years, remainder_months = divmod(months, 12)
    db_session.add(
        HousingHistory(
            application_id=application_id,
            sequence=0,
            street_address="1 Main St",
            city="Fort Wayne",
            state="IN",
            zip="46802",
            housing_status=HousingStatus.RENT,
            residence_years=years,
            residence_months=remainder_months,
        )
    )
    await db_session.flush()


async def test_auto_fix_rules(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    party = ApplicationParty(
        application_id=application.id,
        role=PartyRole.BORROWER,
        first_name="Ben",
        last_name="Ford",
        cell_phone="2605551234",
        home_phone=None,
        ssn_encrypted="123456789",
        dob=date(1990, 1, 1),
    )
    db_session.add(party)
    # Long-enough housing history so `housing_history_24mo` doesn't also fire.
    await _add_current_residence(db_session, application.id, months=36)
    await db_session.flush()

    await run_and_persist(application.id, db_session)

    refreshed = (
        await db_session.execute(
            select(ApplicationParty).where(ApplicationParty.application_id == application.id)
        )
    ).scalar_one()
    assert refreshed.home_phone == "2605551234"
    assert refreshed.no_co_applicant_check is True

    flags = (
        (await db_session.execute(select(Flag).where(Flag.application_id == application.id)))
        .scalars()
        .all()
    )
    flagged_field_keys = {f.field_key for f in flags}
    assert "borrower_home_phone" not in flagged_field_keys
    assert "no_co_applicant_check" not in flagged_field_keys


async def test_run_and_persist_flags_thin_housing_history(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    db_session.add(
        ApplicationParty(
            application_id=application.id,
            role=PartyRole.BORROWER,
            first_name="Ben",
            last_name="Ford",
            cell_phone="2605551234",
            ssn_encrypted="123456789",
            dob=date(1990, 1, 1),
        )
    )
    await _add_current_residence(db_session, application.id, months=14)
    await db_session.flush()

    await run_and_persist(application.id, db_session)

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


async def test_write_flag_upserts(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application(occupancy=Occupancy.INVESTMENT)

    await write_flag(
        db_session,
        application.id,
        ApplicationTab.PRICING,
        "occupancy_type",
        "ob_required_field",
        FlagSeverity.BLOCKING,
    )
    await write_flag(
        db_session,
        application.id,
        ApplicationTab.PRICING,
        "occupancy_type",
        "ob_required_field",
        FlagSeverity.BLOCKING,
    )

    flags = (
        (
            await db_session.execute(
                select(Flag).where(
                    Flag.application_id == application.id,
                    Flag.field_key == "occupancy_type",
                    Flag.rule == "ob_required_field",
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(flags) == 1
    assert flags[0].resolved_at is None
    assert flags[0].severity is FlagSeverity.BLOCKING
