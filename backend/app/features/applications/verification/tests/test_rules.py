"""Pure unit tests for `rules.py` — no DB, no clock, no network.

Covers AC2 (purity), AC4 (SSN/DOB format) and AC5 (pricing-stage rules
self-skip without a priced scenario).
"""

from datetime import date
from decimal import Decimal

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy
from app.features.applications.models import PartyRole
from app.features.applications.verification.rules import evaluate_rules
from app.features.applications.verification.schemas import (
    HousingSnapshot,
    PartySnapshot,
    ScenarioSnapshot,
    VerificationContext,
)

_AS_OF = date(2026, 9, 25)


def _context(**overrides: object) -> VerificationContext:
    defaults: dict[str, object] = dict(
        occupancy=Occupancy.PRIMARY,
        parties=[
            PartySnapshot(
                role=PartyRole.BORROWER,
                cell_phone="4155551234",
                home_phone="4155551234",
                ssn="123456789",
                dob=date(1985, 6, 1),
            )
        ],
        housing_history=[
            HousingSnapshot(sequence=0, residence_years=3, residence_months=0),
        ],
        assets_total=Decimal("50000"),
        liabilities_total=Decimal("500"),
        monthly_income=Decimal("8000"),
        reserves_months=2,
        latest_scenario=None,
        as_of=_AS_OF,
    )
    defaults.update(overrides)
    return VerificationContext(**defaults)  # type: ignore[arg-type]


def test_evaluate_rules_is_pure() -> None:
    """AC2: identical input -> identical output, called twice, no mocks."""
    context = _context(
        latest_scenario=ScenarioSnapshot(
            total_cash_to_close=Decimal("15000.00"),
            total_monthly_payment=Decimal("2200.00"),
        )
    )

    first = evaluate_rules(context)
    second = evaluate_rules(context)

    assert first == second
    assert len(first) > 0


def test_phone_copy_auto_fixes_when_home_phone_missing() -> None:
    context = _context(
        parties=[
            PartySnapshot(
                role=PartyRole.BORROWER,
                cell_phone="4155551234",
                home_phone=None,
                ssn="123456789",
                dob=date(1985, 6, 1),
            )
        ]
    )

    results = evaluate_rules(context)
    phone_result = next(r for r in results if r.rule_id == "phone_copy")

    assert phone_result.passed is True
    assert phone_result.auto_fixed is True
    assert phone_result.fix_value == "4155551234"
    assert phone_result.severity is FlagSeverity.INFO
    assert phone_result.tab is ApplicationTab.BORROWERS
    assert phone_result.field_key == "borrower_home_phone"


def test_phone_copy_no_fix_when_home_phone_present() -> None:
    context = _context()  # home_phone already set in defaults

    results = evaluate_rules(context)
    phone_result = next(r for r in results if r.rule_id == "phone_copy")

    assert phone_result.passed is True
    assert phone_result.auto_fixed is False


def test_no_co_applicant_auto_fixes_when_no_co_borrower() -> None:
    context = _context()  # defaults have only a BORROWER party

    results = evaluate_rules(context)
    result = next(r for r in results if r.rule_id == "no_co_applicant")

    assert result.passed is True
    assert result.auto_fixed is True
    assert result.fix_value is True
    assert result.severity is FlagSeverity.INFO
    assert result.field_key == "no_co_applicant_check"


def test_no_co_applicant_no_fix_when_co_borrower_present() -> None:
    context = _context(
        parties=[
            PartySnapshot(
                role=PartyRole.BORROWER, cell_phone="4155551234", home_phone="4155551234"
            ),
            PartySnapshot(
                role=PartyRole.CO_BORROWER, cell_phone="4155559999", home_phone="4155559999"
            ),
        ]
    )

    results = evaluate_rules(context)
    result = next(r for r in results if r.rule_id == "no_co_applicant")

    assert result.passed is True
    assert result.auto_fixed is False


def test_housing_history_24mo_flags_thin_history() -> None:
    # Persona 8 shape: 14 months at current address, no prior row.
    context = _context(
        housing_history=[HousingSnapshot(sequence=0, residence_years=1, residence_months=2)]
    )

    results = evaluate_rules(context)
    result = next(r for r in results if r.rule_id == "housing_history_24mo")

    assert result.passed is False
    assert result.severity is FlagSeverity.BLOCKING
    assert result.tab is ApplicationTab.HOUSING
    assert result.field_key == "current_residence_years"


def test_housing_history_24mo_passes_with_prior_address_covering_gap() -> None:
    context = _context(
        housing_history=[
            HousingSnapshot(sequence=0, residence_years=1, residence_months=2),
            HousingSnapshot(sequence=1, residence_years=5, residence_months=0),
        ]
    )

    results = evaluate_rules(context)
    result = next(r for r in results if r.rule_id == "housing_history_24mo")

    assert result.passed is True


def test_ssn_dob_format() -> None:
    """AC4: malformed SSN (8 digits) and an invalid DOB (future date) raise
    `blocking` flags; well-formed input passes."""
    bad_context = _context(
        parties=[
            PartySnapshot(
                role=PartyRole.BORROWER,
                ssn="12345678",  # 8 digits, not 9
                dob=date(2099, 1, 1),  # future
            )
        ]
    )
    results = evaluate_rules(bad_context)
    ssn_result = next(r for r in results if r.rule_id == "ssn_format")
    dob_result = next(r for r in results if r.rule_id == "dob_format")

    assert ssn_result.passed is False
    assert ssn_result.severity is FlagSeverity.BLOCKING
    assert ssn_result.field_key == "borrower_ssn"
    assert dob_result.passed is False
    assert dob_result.severity is FlagSeverity.BLOCKING
    assert dob_result.field_key == "borrower_dob"

    good_context = _context()  # ssn=123456789, dob=1985-06-01 in defaults
    good_results = evaluate_rules(good_context)
    assert next(r for r in good_results if r.rule_id == "ssn_format").passed is True
    assert next(r for r in good_results if r.rule_id == "dob_format").passed is True


def test_ssn_format_accepts_hyphenated_input() -> None:
    context = _context(
        parties=[PartySnapshot(role=PartyRole.BORROWER, ssn="123-45-6789", dob=date(1985, 6, 1))]
    )
    results = evaluate_rules(context)
    assert next(r for r in results if r.rule_id == "ssn_format").passed is True


def test_pricing_stage_rules_skip_without_scenario() -> None:
    """AC5: assets_vs_ctc_reserves / dti_primary are skipped entirely
    (no RuleResult at all) when latest_scenario is None."""
    context = _context(latest_scenario=None)

    results = evaluate_rules(context)
    rule_ids = {r.rule_id for r in results}

    assert "assets_vs_ctc_reserves" not in rule_ids
    assert "dti_primary" not in rule_ids


def test_pricing_stage_rules_evaluate_once_scenario_supplied() -> None:
    scenario = ScenarioSnapshot(
        total_cash_to_close=Decimal("15000.00"), total_monthly_payment=Decimal("2000.00")
    )

    # Sufficient assets, low DTI -> both pass.
    passing = _context(
        assets_total=Decimal("30000.00"),
        liabilities_total=Decimal("200.00"),
        monthly_income=Decimal("10000.00"),
        reserves_months=2,
        latest_scenario=scenario,
    )
    results = evaluate_rules(passing)
    assets_result = next(r for r in results if r.rule_id == "assets_vs_ctc_reserves")
    dti_result = next(r for r in results if r.rule_id == "dti_primary")
    assert assets_result.passed is True
    assert assets_result.tab is ApplicationTab.ASSETS
    assert assets_result.field_key == "total_verified_assets"
    assert dti_result.passed is True
    assert dti_result.severity is FlagSeverity.WARNING
    assert dti_result.tab is ApplicationTab.CREDIT
    assert dti_result.field_key == "dti_ratio"

    # Insufficient assets (below CTC + 2 * payment), high DTI -> both fail.
    failing = _context(
        assets_total=Decimal("10000.00"),
        liabilities_total=Decimal("3000.00"),
        monthly_income=Decimal("5000.00"),
        reserves_months=2,
        latest_scenario=scenario,
    )
    results = evaluate_rules(failing)
    assert next(r for r in results if r.rule_id == "assets_vs_ctc_reserves").passed is False
    assert next(r for r in results if r.rule_id == "dti_primary").passed is False


def test_dti_primary_skips_on_investment_occupancy() -> None:
    scenario = ScenarioSnapshot(
        total_cash_to_close=Decimal("15000.00"), total_monthly_payment=Decimal("2000.00")
    )
    context = _context(occupancy=Occupancy.INVESTMENT, latest_scenario=scenario)

    results = evaluate_rules(context)
    assert "dti_primary" not in {r.rule_id for r in results}
    # assets rule still runs regardless of occupancy.
    assert "assets_vs_ctc_reserves" in {r.rule_id for r in results}
