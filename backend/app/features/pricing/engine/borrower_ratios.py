"""Borrower-side money ratios for the verification tabs (CQ-028, plan.md #10).

Kept inside the engine package so money math lives in one place (AGENTS.md):
the Credit tab's DTI and the Assets tab's reserves/sufficiency check. Pure
`Decimal` functions, no I/O. Same formulas as CQ-012's `dti_primary` and
`assets_vs_ctc_reserves` rules.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")
_RATIO_4DP = Decimal("0.0001")


def debt_to_income_ratio(
    monthly_liabilities: Decimal, housing_payment: Decimal, monthly_income: Decimal
) -> Decimal | None:
    """Back-end DTI as a 0-1 fraction, rounded to 4 dp. `None` when monthly
    income is zero or negative (DTI cannot be computed)."""
    if monthly_income <= 0:
        return None
    ratio = (monthly_liabilities + housing_payment) / monthly_income
    return ratio.quantize(_RATIO_4DP, rounding=ROUND_HALF_UP)


def reserves_required_amount(reserves_months: int, total_monthly_payment: Decimal) -> Decimal:
    """Required reserves: `reserves_months` x the monthly PITIA payment."""
    return (Decimal(reserves_months) * total_monthly_payment).quantize(
        _CENTS, rounding=ROUND_HALF_UP
    )


def required_funds_amount(cash_to_close: Decimal, reserves_required: Decimal) -> Decimal:
    """Cash to close plus required reserves."""
    return (cash_to_close + reserves_required).quantize(_CENTS, rounding=ROUND_HALF_UP)


def assets_sufficient(verified_assets: Decimal, required_funds: Decimal) -> bool:
    """Asset sufficiency (system-design "Assets & income"): assets >= cash to
    close + reserves."""
    return verified_assets >= required_funds
