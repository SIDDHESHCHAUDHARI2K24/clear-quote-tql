"""Flag messages (P5/P6 foundation, phase-p5-p6-plan.md E8): every rule
that can raise a `flags` row has human-readable text, and `write_flag`
stores it."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, ApplicationTab, FlagSeverity, UserRole
from app.features.applications.models import Application
from app.features.applications.verification.rules import (
    RULE_MESSAGES,
    field_label,
    flag_message,
)
from app.features.applications.verification.service import write_flag
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.pricing.scenarios.dscr_loop import DSCR_BUCKET_UNSTABLE_RULE

# Every rule id that can write a non-info `flags` row.
FLAG_RAISING_RULES = {
    "housing_history_24mo",
    "ssn_format",
    "dob_format",
    "assets_vs_ctc_reserves",
    "dti_primary",
    DSCR_BUCKET_UNSTABLE_RULE,
}


def test_every_flag_raising_rule_has_a_message() -> None:
    assert FLAG_RAISING_RULES <= set(RULE_MESSAGES)
    for rule in FLAG_RAISING_RULES:
        assert flag_message(rule, "any_field") == RULE_MESSAGES[rule]


@pytest.mark.parametrize(
    ("field_key", "expected"),
    [
        ("occupancy_type", "Cannot price: missing Occupancy"),
        ("RepresentativeFICO", "Cannot price: missing Representative FICO"),
        ("PurchasePrice", "Cannot price: missing Purchase Price"),
        ("LTV", "Cannot price: missing LTV"),
    ],
)
def test_ob_required_field_message_names_the_field(field_key: str, expected: str) -> None:
    assert flag_message("ob_required_field", field_key) == expected


def test_unknown_rule_falls_back_to_field_label() -> None:
    assert flag_message("something_new", "borrower_home_phone") == "Check Borrower home phone."
    assert field_label("borrower_ssn") == "Borrower ssn"


async def _make_application(db: AsyncSession) -> Application:
    lo = User(
        email=f"{uuid.uuid4()}@clearquote.test", password_hash="x", role=UserRole.LO, full_name="L"
    )
    db.add(lo)
    await db.flush()
    client = Client(full_name="C", email=f"{uuid.uuid4()}@x.test", assigned_lo_id=lo.id)
    db.add(client)
    await db.flush()
    application = Application(client_id=client.id, lo_id=lo.id, status=ApplicationStatus.INTAKE)
    db.add(application)
    await db.flush()
    return application


async def test_write_flag_defaults_message_from_rule(db_session: AsyncSession) -> None:
    application = await _make_application(db_session)
    flag = await write_flag(
        db_session,
        application.id,
        ApplicationTab.PRICING,
        "occupancy_type",
        "ob_required_field",
        FlagSeverity.BLOCKING,
    )
    assert flag.message == "Cannot price: missing Occupancy"


async def test_write_flag_stores_explicit_message_and_refreshes_it(
    db_session: AsyncSession,
) -> None:
    application = await _make_application(db_session)
    first = await write_flag(
        db_session,
        application.id,
        ApplicationTab.HOUSING,
        "current_residence_years",
        "housing_history_24mo",
        FlagSeverity.BLOCKING,
        message="Only 14 months of housing history on file; 24 required.",
    )
    assert first.message == "Only 14 months of housing history on file; 24 required."

    again = await write_flag(
        db_session,
        application.id,
        ApplicationTab.HOUSING,
        "current_residence_years",
        "housing_history_24mo",
        FlagSeverity.BLOCKING,
        message="Only 20 months of housing history on file; 24 required.",
    )
    assert again.id == first.id
    assert again.message == "Only 20 months of housing history on file; 24 required."
