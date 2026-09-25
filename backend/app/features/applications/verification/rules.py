"""The 1003 verification rule engine.

`evaluate_rules` is a pure function: given the same `VerificationContext` it
always returns the same `list[RuleResult]`, with no DB session, no clock
(the one clock read `dob_format` needs lives on `VerificationContext.as_of`,
captured once by `service._build_context`) and no network.

Two run times (spec.md): `housing_history_24mo`, `ssn_format`, `dob_format`,
`phone_copy` and `no_co_applicant` run at the pipeline's Verify stage
(CQ-011), before any scenario exists — `assets_vs_ctc_reserves` and
`dti_primary` need a priced scenario, so they return no `RuleResult` at all
(skipped, not failed) until `VerificationContext.latest_scenario` is set,
and are re-run by CQ-013's pricing service every time a scenario is
(re)computed.
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy
from app.features.applications.models import PartyRole
from app.features.applications.verification.schemas import (
    PartySnapshot,
    RuleResult,
    VerificationContext,
)

_SSN_PATTERN = re.compile(r"^\d{9}$")
_MIN_HOUSING_MONTHS = 24
_DTI_THRESHOLD = Decimal("0.45")


def _primary_party(parties: list[PartySnapshot]) -> PartySnapshot | None:
    return next((p for p in parties if p.role is PartyRole.BORROWER), None)


def phone_copy(context: VerificationContext) -> RuleResult | None:
    """Auto-fix: copy `cell_phone` to `home_phone` on the primary party when
    `home_phone` is empty and `cell_phone` is set. `info` severity — never
    raises a `flags` row (decision: previous builds broke on Encompass
    rejecting a missing `home_phone`)."""
    primary = _primary_party(context.parties)
    if primary is None:
        return None

    if not primary.home_phone and primary.cell_phone:
        return RuleResult(
            rule_id="phone_copy",
            tab=ApplicationTab.BORROWERS,
            field_key="borrower_home_phone",
            severity=FlagSeverity.INFO,
            passed=True,
            auto_fixed=True,
            fix_value=primary.cell_phone,
            message=f"Copied cell phone {primary.cell_phone} to home phone.",
        )
    return RuleResult(
        rule_id="phone_copy",
        tab=ApplicationTab.BORROWERS,
        field_key="borrower_home_phone",
        severity=FlagSeverity.INFO,
        passed=True,
        message="Home phone already on file.",
    )


def no_co_applicant(context: VerificationContext) -> RuleResult | None:
    """Auto-fix: set `no_co_applicant_check = True` on the primary party when
    no `co_borrower` party row exists. `info` severity — never raises a
    `flags` row (decision: previous builds broke on an unchecked "No
    co-applicant" box in Encompass)."""
    primary = _primary_party(context.parties)
    if primary is None:
        return None

    has_co_borrower = any(p.role is PartyRole.CO_BORROWER for p in context.parties)
    if not has_co_borrower:
        return RuleResult(
            rule_id="no_co_applicant",
            tab=ApplicationTab.BORROWERS,
            field_key="no_co_applicant_check",
            severity=FlagSeverity.INFO,
            passed=True,
            auto_fixed=True,
            fix_value=True,
            message="No co-borrower on file; checked 'No co-applicant'.",
        )
    return RuleResult(
        rule_id="no_co_applicant",
        tab=ApplicationTab.BORROWERS,
        field_key="no_co_applicant_check",
        severity=FlagSeverity.INFO,
        passed=True,
        message="Co-borrower present.",
    )


def housing_history_24mo(context: VerificationContext) -> RuleResult | None:
    """Flag if the summed `residence_years*12 + residence_months` across all
    `housing_history` rows is under 24 months — i.e. no prior address on
    file covers the gap left by the current one."""
    total_months = sum(
        row.residence_years * 12 + row.residence_months for row in context.housing_history
    )
    passed = total_months >= _MIN_HOUSING_MONTHS
    return RuleResult(
        rule_id="housing_history_24mo",
        tab=ApplicationTab.HOUSING,
        field_key="current_residence_years",
        severity=FlagSeverity.BLOCKING,
        passed=passed,
        message=(
            "24-month housing history verified."
            if passed
            else f"Only {total_months} months of housing history on file; 24 required."
        ),
    )


def ssn_format(context: VerificationContext) -> RuleResult | None:
    """Flag if the primary party's SSN (stripped of `-`) is not exactly 9
    digits. Checked against `PartySnapshot.ssn`, which is always plaintext
    (see plan.md decision #2 — `EncryptedString` decrypts transparently on
    read)."""
    primary = _primary_party(context.parties)
    if primary is None:
        return None

    stripped = (primary.ssn or "").replace("-", "")
    passed = bool(_SSN_PATTERN.fullmatch(stripped))
    return RuleResult(
        rule_id="ssn_format",
        tab=ApplicationTab.BORROWERS,
        field_key="borrower_ssn",
        severity=FlagSeverity.BLOCKING,
        passed=passed,
        message="SSN format valid." if passed else "SSN must be exactly 9 digits.",
    )


def dob_format(context: VerificationContext) -> RuleResult | None:
    """Flag if the primary party's DOB is missing, or not in the past
    (relative to `context.as_of`)."""
    primary = _primary_party(context.parties)
    if primary is None:
        return None

    dob = primary.dob
    passed = dob is not None and dob < context.as_of
    return RuleResult(
        rule_id="dob_format",
        tab=ApplicationTab.BORROWERS,
        field_key="borrower_dob",
        severity=FlagSeverity.BLOCKING,
        passed=passed,
        message=(
            "Date of birth valid." if passed else "Date of birth is missing or not in the past."
        ),
    )


def assets_vs_ctc_reserves(context: VerificationContext) -> RuleResult | None:
    """Skipped (no `RuleResult`) until a scenario is priced. Once one is,
    flag if `assets_total < total_cash_to_close + reserves_months *
    total_monthly_payment` (override O11)."""
    scenario = context.latest_scenario
    if scenario is None:
        return None

    required = scenario.total_cash_to_close + (
        Decimal(context.reserves_months) * scenario.total_monthly_payment
    )
    passed = context.assets_total >= required
    return RuleResult(
        rule_id="assets_vs_ctc_reserves",
        tab=ApplicationTab.ASSETS,
        field_key="total_verified_assets",
        severity=FlagSeverity.BLOCKING,
        passed=passed,
        message=(
            "Verified assets cover cash to close plus reserves."
            if passed
            else (
                f"Verified assets ${context.assets_total} are below the required "
                f"${required} (cash to close + {context.reserves_months} months reserves)."
            )
        ),
    )


def dti_primary(context: VerificationContext) -> RuleResult | None:
    """Only runs for `occupancy == primary` once a scenario is priced;
    otherwise skipped (no `RuleResult`). Flag (warning) if back-end DTI
    exceeds 45%."""
    if context.occupancy is not Occupancy.PRIMARY:
        return None
    scenario = context.latest_scenario
    if scenario is None:
        return None

    if context.monthly_income <= 0:
        return RuleResult(
            rule_id="dti_primary",
            tab=ApplicationTab.CREDIT,
            field_key="dti_ratio",
            severity=FlagSeverity.WARNING,
            passed=False,
            message="Monthly income is $0; cannot compute DTI.",
        )

    dti = (context.liabilities_total + scenario.total_monthly_payment) / context.monthly_income
    passed = dti <= _DTI_THRESHOLD
    return RuleResult(
        rule_id="dti_primary",
        tab=ApplicationTab.CREDIT,
        field_key="dti_ratio",
        severity=FlagSeverity.WARNING,
        passed=passed,
        message=(
            "DTI within the 45% guideline."
            if passed
            else f"DTI {dti:.1%} exceeds the 45% guideline."
        ),
    )


_RULES = (
    phone_copy,
    no_co_applicant,
    housing_history_24mo,
    ssn_format,
    dob_format,
    assets_vs_ctc_reserves,
    dti_primary,
)


def evaluate_rules(context: VerificationContext) -> list[RuleResult]:
    """Runs every rule against `context`, dropping the ones that skipped
    (returned `None` for missing required input)."""
    return [result for rule in _RULES for result in (rule(context),) if result is not None]
