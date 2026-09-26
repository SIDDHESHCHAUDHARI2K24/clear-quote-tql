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
from collections.abc import Callable
from datetime import date
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

# Per-role field_key for the two-party format rules (system-design's
# Borrowers tab covers "Borrower and co-borrower... validates formats";
# data-field-catalog §1 names `borrower_ssn` vs `co_borrower_ssn` as
# distinct fields, so each party's flag gets its own field_key and can
# resolve independently through `write_flag`'s upsert key).
_SSN_FIELD_KEY: dict[PartyRole, str] = {
    PartyRole.BORROWER: "borrower_ssn",
    PartyRole.CO_BORROWER: "co_borrower_ssn",
}
_DOB_FIELD_KEY: dict[PartyRole, str] = {
    PartyRole.BORROWER: "borrower_dob",
    PartyRole.CO_BORROWER: "co_borrower_dob",
}


def _primary_party(parties: list[PartySnapshot]) -> PartySnapshot | None:
    return next((p for p in parties if p.role is PartyRole.BORROWER), None)


def phone_copy(context: VerificationContext) -> list[RuleResult]:
    """Auto-fix: copy `cell_phone` to `home_phone` on the primary party when
    `home_phone` is empty and `cell_phone` is set. `info` severity — never
    raises a `flags` row (decision: previous builds broke on Encompass
    rejecting a missing `home_phone`)."""
    primary = _primary_party(context.parties)
    if primary is None:
        return []

    if not primary.home_phone and primary.cell_phone:
        return [
            RuleResult(
                rule_id="phone_copy",
                tab=ApplicationTab.BORROWERS,
                field_key="borrower_home_phone",
                severity=FlagSeverity.INFO,
                passed=True,
                auto_fixed=True,
                fix_value=primary.cell_phone,
                message=f"Copied cell phone {primary.cell_phone} to home phone.",
            )
        ]
    return [
        RuleResult(
            rule_id="phone_copy",
            tab=ApplicationTab.BORROWERS,
            field_key="borrower_home_phone",
            severity=FlagSeverity.INFO,
            passed=True,
            message="Home phone already on file.",
        )
    ]


def no_co_applicant(context: VerificationContext) -> list[RuleResult]:
    """Auto-fix: set `no_co_applicant_check = True` on the primary party when
    no `co_borrower` party row exists. `info` severity — never raises a
    `flags` row (decision: previous builds broke on an unchecked "No
    co-applicant" box in Encompass)."""
    primary = _primary_party(context.parties)
    if primary is None:
        return []

    has_co_borrower = any(p.role is PartyRole.CO_BORROWER for p in context.parties)
    if not has_co_borrower:
        return [
            RuleResult(
                rule_id="no_co_applicant",
                tab=ApplicationTab.BORROWERS,
                field_key="no_co_applicant_check",
                severity=FlagSeverity.INFO,
                passed=True,
                auto_fixed=True,
                fix_value=True,
                message="No co-borrower on file; checked 'No co-applicant'.",
            )
        ]
    return [
        RuleResult(
            rule_id="no_co_applicant",
            tab=ApplicationTab.BORROWERS,
            field_key="no_co_applicant_check",
            severity=FlagSeverity.INFO,
            passed=True,
            message="Co-borrower present.",
        )
    ]


def housing_history_24mo(context: VerificationContext) -> list[RuleResult]:
    """Flag if the summed `residence_years*12 + residence_months` across all
    `housing_history` rows is under 24 months — i.e. no prior address on
    file covers the gap left by the current one."""
    total_months = sum(
        row.residence_years * 12 + row.residence_months for row in context.housing_history
    )
    passed = total_months >= _MIN_HOUSING_MONTHS
    return [
        RuleResult(
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
    ]


def _ssn_result(party: PartySnapshot) -> RuleResult:
    stripped = (party.ssn or "").replace("-", "")
    passed = bool(_SSN_PATTERN.fullmatch(stripped))
    return RuleResult(
        rule_id="ssn_format",
        tab=ApplicationTab.BORROWERS,
        field_key=_SSN_FIELD_KEY[party.role],
        severity=FlagSeverity.BLOCKING,
        passed=passed,
        message="SSN format valid." if passed else "SSN must be exactly 9 digits.",
    )


def ssn_format(context: VerificationContext) -> list[RuleResult]:
    """Flag if a party's SSN (stripped of `-`) is not exactly 9 digits.
    Runs for the primary party and, when present, the co-borrower — each
    gets its own `field_key` (`borrower_ssn` / `co_borrower_ssn`) so the two
    can be flagged and resolved independently. Checked against
    `PartySnapshot.ssn`, which is always plaintext (see plan.md decision #2
    — `EncryptedString` decrypts transparently on read)."""
    return [_ssn_result(p) for p in context.parties if p.role in _SSN_FIELD_KEY]


def _dob_result(party: PartySnapshot, as_of: date) -> RuleResult:
    dob = party.dob
    passed = dob is not None and dob < as_of
    return RuleResult(
        rule_id="dob_format",
        tab=ApplicationTab.BORROWERS,
        field_key=_DOB_FIELD_KEY[party.role],
        severity=FlagSeverity.BLOCKING,
        passed=passed,
        message=(
            "Date of birth valid." if passed else "Date of birth is missing or not in the past."
        ),
    )


def dob_format(context: VerificationContext) -> list[RuleResult]:
    """Flag if a party's DOB is missing, or not in the past (relative to
    `context.as_of`). Runs for the primary party and, when present, the
    co-borrower — each gets its own `field_key` (`borrower_dob` /
    `co_borrower_dob`)."""
    return [_dob_result(p, context.as_of) for p in context.parties if p.role in _DOB_FIELD_KEY]


def assets_vs_ctc_reserves(context: VerificationContext) -> list[RuleResult]:
    """Skipped (no `RuleResult`) until a scenario is priced. Once one is,
    flag if `assets_total < total_cash_to_close + reserves_months *
    total_monthly_payment` (override O11)."""
    scenario = context.latest_scenario
    if scenario is None:
        return []

    required = scenario.total_cash_to_close + (
        Decimal(context.reserves_months) * scenario.total_monthly_payment
    )
    passed = context.assets_total >= required
    return [
        RuleResult(
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
    ]


def dti_primary(context: VerificationContext) -> list[RuleResult]:
    """Only runs for `occupancy == primary` once a scenario is priced;
    otherwise skipped (no `RuleResult`). Flag (warning) if back-end DTI
    exceeds 45%."""
    if context.occupancy is not Occupancy.PRIMARY:
        return []
    scenario = context.latest_scenario
    if scenario is None:
        return []

    if context.monthly_income <= 0:
        return [
            RuleResult(
                rule_id="dti_primary",
                tab=ApplicationTab.CREDIT,
                field_key="dti_ratio",
                severity=FlagSeverity.WARNING,
                passed=False,
                message="Monthly income is $0; cannot compute DTI.",
            )
        ]

    dti = (context.liabilities_total + scenario.total_monthly_payment) / context.monthly_income
    passed = dti <= _DTI_THRESHOLD
    return [
        RuleResult(
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
    ]


_RULES: tuple[Callable[[VerificationContext], list[RuleResult]], ...] = (
    phone_copy,
    no_co_applicant,
    housing_history_24mo,
    ssn_format,
    dob_format,
    assets_vs_ctc_reserves,
    dti_primary,
)


def evaluate_rules(context: VerificationContext) -> list[RuleResult]:
    """Runs every rule against `context`, flattening each rule's 0-or-more
    results (a rule returns `[]` when it self-skips for missing required
    input, e.g. no priced scenario yet)."""
    results: list[RuleResult] = []
    for rule in _RULES:
        results.extend(rule(context))
    return results


# --- Flag messages (P5/P6 foundation, phase-p5-p6-plan.md E8) -------------
#
# Static, human-readable text per flag rule id, shown next to the field in
# the verification tabs (CQ-028) and in lists (CQ-025/027). `write_flag`
# stores `flag_message(rule, field_key)` when its caller passes no message
# of its own; `run_and_persist` passes each `RuleResult.message` instead
# (the dynamic text, e.g. "Only 14 months ..."). The foundation migration
# backfills existing `flags` rows with a frozen copy of this table.
#
# `ob_required_field` and `dscr_bucket_unstable` are raised outside this
# module (CQ-013's `pricing/enrichment/service.py` and `pricing/scenarios/
# dscr_loop.py`) but share the same `flags` table, so their text lives here
# too.

OB_REQUIRED_FIELD_RULE = "ob_required_field"

RULE_MESSAGES: dict[str, str] = {
    "housing_history_24mo": (
        "Less than 24 months of housing history on file; add a prior address."
    ),
    "ssn_format": "SSN must be exactly 9 digits.",
    "dob_format": "Date of birth is missing or not in the past.",
    "assets_vs_ctc_reserves": "Verified assets are below cash to close plus required reserves.",
    "dti_primary": "DTI exceeds the 45% guideline.",
    "dscr_bucket_unstable": (
        "DSCR bucket changed between pricing passes; priced at the lower DSCR."
    ),
}

# `flags.field_key` -> the label the LO sees in "Cannot price: missing
# {label}" (persona 7, Aisha Coleman: "Cannot price: missing Occupancy").
_OB_FIELD_LABELS: dict[str, str] = {
    "occupancy_type": "Occupancy",
    "RepresentativeFICO": "Representative FICO",
}

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")


def field_label(field_key: str) -> str:
    """A readable label for a `flags.field_key` (`occupancy_type` ->
    "Occupancy", `PurchasePrice` -> "Purchase Price", `LTV` -> "LTV")."""
    if field_key in _OB_FIELD_LABELS:
        return _OB_FIELD_LABELS[field_key]
    if "_" in field_key:
        return field_key.replace("_", " ").capitalize()
    return _CAMEL_BOUNDARY.sub(" ", field_key)


def flag_message(rule: str, field_key: str) -> str:
    """The default human-readable message for a `flags` row."""
    if rule == OB_REQUIRED_FIELD_RULE:
        return f"Cannot price: missing {field_label(field_key)}"
    return RULE_MESSAGES.get(rule, f"Check {field_label(field_key)}.")
