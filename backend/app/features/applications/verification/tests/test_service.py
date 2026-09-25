"""Integration tests for `service.py` against the real (test) database.

Covers AC3 (auto-fix rules never raise a `flags` row), AC6 (`write_flag`
upserts on `(application_id, field_key, rule)`), and the review-round
follow-ups: `run_and_persist` writes no `activity_events`, flags auto-resolve
when their rule later passes, co-borrower SSN/DOB get their own field_keys,
`latest_scenario_snapshot` reads a real `Quote.computed` blob, and a
malformed SSN is caught through the real encrypted-column round trip.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.features.applications.verification.service import (
    latest_scenario_snapshot,
    run_and_persist,
    write_flag,
)
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote


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


async def _add_priced_quote(
    db_session: AsyncSession,
    application_id: uuid.UUID,
    *,
    cash_to_close: str,
    total_monthly_payment: str,
) -> None:
    scenario = Scenario(application_id=application_id, inputs={}, config_snapshot={})
    db_session.add(scenario)
    await db_session.flush()
    db_session.add(
        Quote(
            scenario_id=scenario.id,
            investor="Test Investor",
            product="Test Product 30yr Fixed",
            rate=Decimal("7.125"),
            points=Decimal("0.000"),
            lock_days=30,
            computed={
                "cash_to_close": cash_to_close,
                "total_monthly_payment": total_monthly_payment,
            },
            label="Par",
            priced_at=datetime.now(UTC),
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

    run_result = await run_and_persist(application.id, db_session)

    refreshed = (
        await db_session.execute(
            select(ApplicationParty).where(ApplicationParty.application_id == application.id)
        )
    ).scalar_one()
    assert refreshed.home_phone == "2605551234"
    assert refreshed.no_co_applicant_check is True

    assert {r.rule_id for r in run_result.auto_fixed} == {"phone_copy", "no_co_applicant"}
    assert run_result.flags_raised == []

    flags = (
        (await db_session.execute(select(Flag).where(Flag.application_id == application.id)))
        .scalars()
        .all()
    )
    flagged_field_keys = {f.field_key for f in flags}
    assert "borrower_home_phone" not in flagged_field_keys
    assert "no_co_applicant_check" not in flagged_field_keys


async def test_run_and_persist_writes_no_activity_events(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """MAJOR review finding: CQ-011 owns activity_events (one row per
    pipeline stage); run_and_persist must not write its own."""
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
    await _add_current_residence(db_session, application.id, months=14)  # also raises a flag
    await db_session.flush()

    await run_and_persist(application.id, db_session)

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(ActivityEvent.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert events == []


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

    run_result = await run_and_persist(application.id, db_session)

    assert {f.rule for f in run_result.flags_raised} == {"housing_history_24mo"}

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


async def test_run_and_persist_resolves_flag_once_rule_passes(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """Raise -> resolve: LO fixes the underlying data, re-running
    run_and_persist resolves the existing flags row rather than leaving it
    open or creating a second one."""
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

    first_run = await run_and_persist(application.id, db_session)
    assert {f.rule for f in first_run.flags_raised} == {"housing_history_24mo"}
    original_flag_id = first_run.flags_raised[0].id

    # LO adds a prior address covering the gap.
    housing_row = (
        await db_session.execute(
            select(HousingHistory).where(HousingHistory.application_id == application.id)
        )
    ).scalar_one()
    housing_row.residence_years = 3
    housing_row.residence_months = 0
    await db_session.flush()

    second_run = await run_and_persist(application.id, db_session)
    assert {f.rule for f in second_run.flags_resolved} == {"housing_history_24mo"}
    assert second_run.flags_raised == []

    flags = (
        (
            await db_session.execute(
                select(Flag).where(
                    Flag.application_id == application.id, Flag.rule == "housing_history_24mo"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(flags) == 1  # resolved in place, not duplicated
    assert flags[0].id == original_flag_id
    assert flags[0].resolved_at is not None


async def test_run_and_persist_leaves_flag_open_when_still_failing(
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
    second_run = await run_and_persist(application.id, db_session)  # still thin, unchanged

    assert second_run.flags_resolved == []
    assert {f.rule for f in second_run.flags_raised} == {"housing_history_24mo"}

    flags = (
        (
            await db_session.execute(
                select(Flag).where(
                    Flag.application_id == application.id, Flag.rule == "housing_history_24mo"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(flags) == 1
    assert flags[0].resolved_at is None


async def test_ssn_dob_validate_co_borrower_with_distinct_field_keys(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    db_session.add(
        ApplicationParty(
            application_id=application.id,
            role=PartyRole.BORROWER,
            first_name="Tom",
            last_name="Brandt",
            cell_phone="2165551234",
            ssn_encrypted="123456789",
            dob=date(1980, 1, 1),
        )
    )
    db_session.add(
        ApplicationParty(
            application_id=application.id,
            role=PartyRole.CO_BORROWER,
            first_name="Lisa",
            last_name="Brandt",
            cell_phone="2165559999",
            ssn_encrypted="12345678",  # malformed: 8 digits
            dob=date(2099, 1, 1),  # future
        )
    )
    await _add_current_residence(db_session, application.id, months=36)
    await db_session.flush()

    run_result = await run_and_persist(application.id, db_session)

    flags_by_field_key = {f.field_key: f for f in run_result.flags_raised}
    assert "borrower_ssn" not in flags_by_field_key
    assert "borrower_dob" not in flags_by_field_key
    assert "co_borrower_ssn" in flags_by_field_key
    assert "co_borrower_dob" in flags_by_field_key
    assert flags_by_field_key["co_borrower_ssn"].rule == "ssn_format"
    assert flags_by_field_key["co_borrower_dob"].rule == "dob_format"


async def test_run_and_persist_flags_malformed_ssn_via_db_decrypt_roundtrip(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """Exercises the real `EncryptedString` decrypt path (not a hand-built
    `PartySnapshot`): `db.refresh` forces the ORM to re-read the column from
    Postgres, decrypting the stored Fernet token back to plaintext."""
    application = await make_application()
    party = ApplicationParty(
        application_id=application.id,
        role=PartyRole.BORROWER,
        first_name="Test",
        last_name="Borrower",
        cell_phone="5551234567",
        ssn_encrypted="12345678",  # malformed: 8 digits
        dob=date(1990, 1, 1),
    )
    db_session.add(party)
    await _add_current_residence(db_session, application.id, months=36)
    await db_session.flush()
    await db_session.refresh(party)  # forces process_result_value (decrypt) to run

    run_result = await run_and_persist(application.id, db_session)

    ssn_result = next(r for r in run_result.rule_results if r.rule_id == "ssn_format")
    assert ssn_result.passed is False
    assert ssn_result.field_key == "borrower_ssn"

    flag = (
        await db_session.execute(
            select(Flag).where(Flag.application_id == application.id, Flag.rule == "ssn_format")
        )
    ).scalar_one()
    assert flag.field_key == "borrower_ssn"
    assert flag.resolved_at is None


async def test_latest_scenario_snapshot_reads_quote_computed(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    await _add_priced_quote(
        db_session,
        application.id,
        cash_to_close="15234.56",
        total_monthly_payment="2201.34",
    )

    snapshot = await latest_scenario_snapshot(db_session, application.id)

    assert snapshot is not None
    assert snapshot.total_cash_to_close == Decimal("15234.56")
    assert snapshot.total_monthly_payment == Decimal("2201.34")


async def test_run_and_persist_evaluates_pricing_rules_against_real_quote(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """End to end: once a Quote row exists, run_and_persist's assembled
    context carries a non-None latest_scenario, so assets_vs_ctc_reserves
    and dti_primary actually evaluate instead of self-skipping."""
    application = await make_application(occupancy=Occupancy.PRIMARY)
    db_session.add(
        ApplicationParty(
            application_id=application.id,
            role=PartyRole.BORROWER,
            first_name="Priya",
            last_name="Nair",
            cell_phone="3175551234",
            ssn_encrypted="123456789",
            dob=date(1985, 1, 1),
        )
    )
    await _add_current_residence(db_session, application.id, months=36)
    await _add_priced_quote(
        db_session, application.id, cash_to_close="10000.00", total_monthly_payment="2000.00"
    )
    await db_session.flush()

    run_result = await run_and_persist(application.id, db_session)

    rule_ids = {r.rule_id for r in run_result.rule_results}
    assert "assets_vs_ctc_reserves" in rule_ids
    assert "dti_primary" in rule_ids


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
