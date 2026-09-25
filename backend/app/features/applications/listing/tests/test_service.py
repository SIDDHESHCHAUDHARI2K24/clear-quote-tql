"""`listing.service` unit tests: AC3 (`sent_or_later` == the dashboard's
"Pre-approvals sent" definition) plus the row-shape helpers (property
label, strategy label, flag count) that don't need the HTTP layer."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Strategy, UserRole
from app.features.applications.listing.service import list_applications
from app.features.applications.listing.tests.conftest import (
    MakeApplication,
    MakeLo,
    add_flag,
    add_sent_quote_package,
    add_specific_property,
    add_tbd_property,
)


async def test_sent_or_later_matches_dashboard_definition(
    db_session: AsyncSession, make_lo: MakeLo, make_application: MakeApplication
) -> None:
    """spec.md AC3 / plan.md Decision #6: "Sent, Viewed, Inquiry,
    OptionSelected, and Stale after a send" -- a Stale application that was
    *never* sent (it aged out straight from Priced, per CQ-030 spec.md)
    must NOT count, and every other pre-Stale status must NOT count."""
    manager = await make_lo("Manager", UserRole.MANAGER)

    sent = await make_application(lo=manager, status=ApplicationStatus.SENT)
    await add_sent_quote_package(db_session, sent.application)
    viewed = await make_application(lo=manager, status=ApplicationStatus.VIEWED)
    await add_sent_quote_package(db_session, viewed.application)
    inquiry = await make_application(lo=manager, status=ApplicationStatus.INQUIRY)
    await add_sent_quote_package(db_session, inquiry.application)
    option_selected = await make_application(lo=manager, status=ApplicationStatus.OPTION_SELECTED)
    await add_sent_quote_package(db_session, option_selected.application)
    stale_after_send = await make_application(lo=manager, status=ApplicationStatus.STALE)
    await add_sent_quote_package(db_session, stale_after_send.application)

    stale_never_sent = await make_application(lo=manager, status=ApplicationStatus.STALE)
    priced_never_sent = await make_application(lo=manager, status=ApplicationStatus.PRICED)
    intake = await make_application(lo=manager, status=ApplicationStatus.INTAKE)

    page = await list_applications(db_session, manager, status="sent_or_later", page_size=100)

    ids = {row.id for row in page.items}
    assert ids == {
        sent.application.id,
        viewed.application.id,
        inquiry.application.id,
        option_selected.application.id,
        stale_after_send.application.id,
    }
    assert stale_never_sent.application.id not in ids
    assert priced_never_sent.application.id not in ids
    assert intake.application.id not in ids


async def test_property_label_specific_address(
    db_session: AsyncSession, make_lo: MakeLo, make_application: MakeApplication
) -> None:
    manager = await make_lo("Manager", UserRole.MANAGER)
    fixture = await make_application(lo=manager)
    await add_specific_property(
        db_session, fixture.application, street_address="1500 Larimer St", city="Denver", state="CO"
    )

    page = await list_applications(db_session, manager, page_size=100)
    row = next(r for r in page.items if r.id == fixture.application.id)
    assert row.property_label == "1500 Larimer St, Denver, CO"


async def test_property_label_tbd(
    db_session: AsyncSession, make_lo: MakeLo, make_application: MakeApplication
) -> None:
    manager = await make_lo("Manager", UserRole.MANAGER)
    fixture = await make_application(lo=manager)
    await add_tbd_property(db_session, fixture.application, buy_box_metros=["Davenport", "Orlando"])

    page = await list_applications(db_session, manager, page_size=100)
    row = next(r for r in page.items if r.id == fixture.application.id)
    assert row.property_label == "TBD · Davenport, Orlando"


async def test_property_label_missing_property_row(
    db_session: AsyncSession, make_lo: MakeLo, make_application: MakeApplication
) -> None:
    manager = await make_lo("Manager", UserRole.MANAGER)
    fixture = await make_application(lo=manager)

    page = await list_applications(db_session, manager, page_size=100)
    row = next(r for r in page.items if r.id == fixture.application.id)
    assert row.property_label is None


async def test_strategy_label_ignores_occupancy(
    db_session: AsyncSession, make_lo: MakeLo, make_application: MakeApplication
) -> None:
    """A Coleman-like row: the LOS record's `occupancy_type` is missing
    (`applications.occupancy` is `NULL`) but `strategy` is `ltr` -- the row
    must still show/filter as `ltr`, not fall through to `primary`."""
    manager = await make_lo("Manager", UserRole.MANAGER)
    fixture = await make_application(lo=manager, strategy=Strategy.LTR)

    page = await list_applications(db_session, manager, strategy="ltr", page_size=100)
    assert {r.id for r in page.items} == {fixture.application.id}

    row = next(r for r in page.items)
    assert row.strategy == "ltr"


async def test_flag_count_only_unresolved(
    db_session: AsyncSession, make_lo: MakeLo, make_application: MakeApplication
) -> None:
    manager = await make_lo("Manager", UserRole.MANAGER)
    fixture = await make_application(lo=manager, status=ApplicationStatus.NEEDS_ATTENTION)
    await add_flag(db_session, fixture.application, resolved=False)
    await add_flag(db_session, fixture.application, rule="other_rule", resolved=True)

    page = await list_applications(db_session, manager, page_size=100)
    row = next(r for r in page.items if r.id == fixture.application.id)
    assert row.flag_count == 1
