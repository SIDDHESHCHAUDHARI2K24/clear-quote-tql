"""Types for the pure quote calculation engine.

`ScenarioInputs`, `ConfigSnapshot` and `QuoteComputation` are implemented as
stdlib `@dataclass(frozen=True, kw_only=True)` rather than Pydantic v2 models
(see docs/backlog/CQ-008-quote-engine/plan.md, Decision 2): this item must not
add a new project dependency, and pydantic is not yet declared in
pyproject.toml. Dataclasses give the same immutability guarantee with zero
I/O and zero new dependency; `kw_only=True` lets defaulted and non-defaulted
fields interleave in the spec's documented order.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.features.pricing.engine.mi_matrix import DEFAULT_MI_MATRIX, MiMatrix


class StrategyType(StrEnum):
    """The engine's single occupancy/strategy field.

    Mapping from `applications.occupancy` + `applications.strategy` (CQ-007)
    onto this enum is CQ-013's job, not this item's.
    """

    PRIMARY = "PRIMARY"
    LTR = "LTR"
    STR = "STR"


class DSCRBucket(StrEnum):
    """DSCR classification bucket. Boundaries are inclusive on the lower edge."""

    BELOW_1_00 = "BELOW_1_00"
    ONE_TO_1_25 = "ONE_TO_1_25"
    GE_1_25 = "GE_1_25"


@dataclass(frozen=True, kw_only=True)
class ScenarioInputs:
    """A scenario's inputs to the calculation engine. All money/rate fields are Decimal.

    `market_rent_ltr` is required (and only meaningful) when `strategy == LTR`;
    `str_gross_annual_revenue` is required (and only meaningful) when
    `strategy == STR`; both are `None` for `PRIMARY`.
    """

    purchase_price: Decimal
    down_payment_pct: Decimal
    note_rate: Decimal
    strategy: StrategyType
    fico: int
    property_tax_annual_rate: Decimal
    insurance_annual_rate: Decimal
    term_months: int = 360
    hoa_monthly: Decimal = Decimal("0")
    discount_points_pct: Decimal = Decimal("0")
    seller_credits: Decimal = Decimal("0")
    market_rent_ltr: Decimal | None = None
    str_gross_annual_revenue: Decimal | None = None
    target_dscr: Decimal | None = None
    bonus_depreciation_pct: Decimal | None = None
    investor_marginal_tax_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if self.strategy is StrategyType.LTR:
            if self.market_rent_ltr is None:
                raise ValueError("market_rent_ltr is required when strategy == LTR")
            if self.str_gross_annual_revenue is not None:
                raise ValueError("str_gross_annual_revenue must be None when strategy == LTR")
        elif self.strategy is StrategyType.STR:
            if self.str_gross_annual_revenue is None:
                raise ValueError("str_gross_annual_revenue is required when strategy == STR")
            if self.market_rent_ltr is not None:
                raise ValueError("market_rent_ltr must be None when strategy == STR")
        else:  # PRIMARY
            if self.market_rent_ltr is not None or self.str_gross_annual_revenue is not None:
                raise ValueError(
                    "market_rent_ltr and str_gross_annual_revenue must be None when "
                    "strategy == PRIMARY"
                )


@dataclass(frozen=True, kw_only=True)
class ConfigSnapshot:
    """Pricing configuration, snapshotted per-quote so old quotes never change
    when defaults change later (`scenarios.config_snapshot` stores one of
    these as JSON per CQ-007).
    """

    lender_processing_fee: Decimal = Decimal("995.00")
    lender_underwriting_fee: Decimal = Decimal("795.00")
    title_rate_pct: Decimal = Decimal("0.007")
    insurance_rate_pct: Decimal = Decimal("0.005")
    prepaid_interest_days: int = 15
    prepaid_insurance_months: int = 14
    prepaid_tax_months: int = 3
    str_expense_ratio: Decimal = Decimal("0.20")
    cap_rate_multiplier: Decimal = Decimal("0.75")
    land_allocation_pct: Decimal = Decimal("0.20")
    accelerated_property_pct: Decimal = Decimal("0.25")
    bonus_depreciation_pct: Decimal = Decimal("1.00")
    investor_marginal_tax_rate: Decimal = Decimal("0.32")
    target_dscr: Decimal = Decimal("1.00")
    reserves_months_primary: int = 2
    reserves_months_investment: int = 6
    mi_matrix: MiMatrix = DEFAULT_MI_MATRIX


@dataclass(frozen=True, kw_only=True)
class QuoteComputation:
    """Every money number Clear Quote shows, computed once by `compute_quote`.

    All currency fields are `Decimal` rounded to cents; `dscr_ratio` is
    rounded to 2dp; `cap_rate_pct` is rounded to 2dp of percent (e.g. `6.42`
    means 6.42%). Investment-only fields are `None` on `PRIMARY` scenarios —
    primary loans never carry rent/DSCR/cashflow/cost-seg numbers.
    """

    loan_amount: Decimal
    ltv_pct: Decimal
    monthly_pi: Decimal
    monthly_tax: Decimal
    monthly_insurance: Decimal
    monthly_mi: Decimal | None
    monthly_hoa: Decimal
    total_monthly_payment: Decimal
    discount_points_amount: Decimal
    lender_fees: Decimal
    title_fees: Decimal
    prepaid_interest: Decimal
    prepaid_insurance: Decimal
    prepaid_taxes: Decimal
    total_prepaids: Decimal
    total_closing_costs: Decimal
    cash_to_close: Decimal
    config_snapshot: ConfigSnapshot

    # Investment-only (LTR/STR); always None on PRIMARY.
    qualifying_rent: Decimal | None = None
    underwritten_str_rent: Decimal | None = None
    dscr_ratio: Decimal | None = None
    dscr_bucket: DSCRBucket | None = None
    monthly_cashflow: Decimal | None = None
    annual_cashflow: Decimal | None = None
    break_even_rent_ltr: Decimal | None = None
    str_annual_rent_target: Decimal | None = None
    cap_rate_pct: Decimal | None = None
    land_value_allocation: Decimal | None = None
    depreciable_building_basis: Decimal | None = None
    accelerated_basis_amount: Decimal | None = None
    year_one_tax_deduction: Decimal | None = None
    year_one_tax_savings: Decimal | None = None
    monthly_cashflow_incl_tax: Decimal | None = None
