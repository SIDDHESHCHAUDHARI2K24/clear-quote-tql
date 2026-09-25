"""Pure-Python types for the verification rule engine.

`VerificationContext` is everything `evaluate_rules` (`rules.py`) needs to
know about an application; `RuleResult` is everything `service.py` needs to
persist one rule's outcome. Neither type touches the DB, a clock or the
network — `service.py` assembles a `VerificationContext` (including
`as_of`, the one clock read the rules need for `dob_format`) and interprets
the `list[RuleResult]` `evaluate_rules` returns.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy
from app.features.applications.models import PartyRole


class PartySnapshot(BaseModel):
    """One `application_parties` row, trimmed to what the rules need."""

    role: PartyRole
    cell_phone: str | None = None
    home_phone: str | None = None
    ssn: str | None = None
    dob: date | None = None


class HousingSnapshot(BaseModel):
    """One `housing_history` row, trimmed to what `housing_history_24mo` needs."""

    sequence: int
    residence_years: int
    residence_months: int


class ScenarioSnapshot(BaseModel):
    """The two `quote_engine`-computed numbers the pricing-stage rules read.

    Field names match `data-field-catalog.md`'s `total_cash_to_close` /
    `total_monthly_payment`, not CQ-008's `QuoteComputation.cash_to_close`
    (`service.py` maps between the two when assembling this).
    """

    total_cash_to_close: Decimal
    total_monthly_payment: Decimal


class RuleResult(BaseModel):
    """One rule's outcome for one application, as pinned by spec.md."""

    rule_id: str
    tab: ApplicationTab
    field_key: str
    severity: FlagSeverity
    passed: bool
    message: str
    auto_fixed: bool = False
    fix_value: Any | None = None


class VerificationContext(BaseModel):
    """Everything `evaluate_rules` needs, assembled by `service._build_context`."""

    occupancy: Occupancy
    parties: list[PartySnapshot]
    housing_history: list[HousingSnapshot]
    assets_total: Decimal
    liabilities_total: Decimal
    monthly_income: Decimal
    reserves_months: int
    latest_scenario: ScenarioSnapshot | None = None
    as_of: date
    """The one clock read `dob_format` needs ("not in the past"), captured
    once by `service.py` so `evaluate_rules` stays a pure function of its
    input (decision #3, plan.md)."""
