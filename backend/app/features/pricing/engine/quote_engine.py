"""Pure quote calculation engine.

`compute_quote` turns a scenario's inputs into every money number Clear Quote
shows (P&I, PITIA, cash to close, DSCR, cashflow, cap rate, cost
segregation), so the LO preview, borrower report and PDFs are always the same
numbers computed the same way. No I/O, no DB, no network.

Rounding rule (pinned in spec.md): the entire calculation chain runs in
unrounded `Decimal` (Python's default 28-significant-digit context); every
downstream formula reads the *unrounded* upstream value, never a previously
rounded field. `ROUND_HALF_UP` is applied exactly once per field, only when
populating `QuoteComputation`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.features.pricing.engine.mi_matrix import mi_factor
from app.features.pricing.engine.types import (
    ConfigSnapshot,
    DSCRBucket,
    QuoteComputation,
    ScenarioInputs,
    StrategyType,
)

_CENT = Decimal("0.01")
# ltv_pct is a 0-1 fraction (unlike currency/dscr/cap-rate fields, which are
# 2dp); 4dp preserves the same display precision as "2dp of percent" (e.g.
# 0.8750 == 87.50%).
_LTV_PRECISION = Decimal("0.0001")
_MAX_PRIMARY_LTV = Decimal("0.97")


class LtvOutOfRangeError(ValueError):
    """Raised by `compute_quote` when a PRIMARY scenario's LTV exceeds the
    conventional financing maximum (97%). Not raised by `mi_factor` itself,
    which is a pure lookup with no notion of a program maximum."""


def _round_currency(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _round_2dp(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _round_ltv(value: Decimal) -> Decimal:
    return value.quantize(_LTV_PRECISION, rounding=ROUND_HALF_UP)


# --- Payment -----------------------------------------------------------------


def loan_amount(purchase_price: Decimal, down_payment_pct: Decimal) -> Decimal:
    """`L = P x (1 - d)`."""
    return purchase_price * (Decimal("1") - down_payment_pct)


def ltv_pct(down_payment_pct: Decimal) -> Decimal:
    """LTV as a 0-1 fraction: `1 - d`."""
    return Decimal("1") - down_payment_pct


def principal_and_interest(loan: Decimal, note_rate: Decimal, term_months: int) -> Decimal:
    """`P&I = L * r(1+r)^n / ((1+r)^n - 1)`, `r = note_rate / 12`, `n = term_months`."""
    r = note_rate / Decimal("12")
    n = term_months
    if r == 0:
        return loan / Decimal(n)
    one_plus_r_n = (Decimal("1") + r) ** n
    return loan * r * one_plus_r_n / (one_plus_r_n - Decimal("1"))


def monthly_tax_amount(purchase_price: Decimal, property_tax_annual_rate: Decimal) -> Decimal:
    return purchase_price * property_tax_annual_rate / Decimal("12")


def monthly_insurance_amount(purchase_price: Decimal, insurance_annual_rate: Decimal) -> Decimal:
    return purchase_price * insurance_annual_rate / Decimal("12")


def monthly_mi_amount(
    loan: Decimal,
    ltv_fraction: Decimal,
    fico: int,
    strategy: StrategyType,
    config: ConfigSnapshot,
) -> Decimal | None:
    """`0` unless `strategy == PRIMARY` and a matrix factor applies (LTV > 80%).

    Callers must guard `ltv_fraction > 0.97` themselves (`compute_quote` raises
    `LtvOutOfRangeError`) — this function does not raise, only looks up.
    """
    if strategy is not StrategyType.PRIMARY:
        return None
    factor = mi_factor(ltv_fraction, fico, config)
    if factor is None:
        return None
    return loan * factor / Decimal("12")


def total_monthly_payment(
    pi: Decimal,
    tax: Decimal,
    insurance: Decimal,
    mi: Decimal | None,
    hoa: Decimal,
) -> Decimal:
    """PITIA = P&I + tax + insurance + MI + HOA."""
    return pi + tax + insurance + (mi or Decimal("0")) + hoa


# --- Cash to close -------------------------------------------------------------


def discount_points_amount(discount_points_pct: Decimal, loan: Decimal) -> Decimal:
    """Negative `discount_points_pct` yields a negative amount (a credit)."""
    return discount_points_pct * loan


def title_fees_amount(purchase_price: Decimal, title_rate_pct: Decimal) -> Decimal:
    return purchase_price * title_rate_pct


def total_prepaids_amount(
    pi: Decimal,
    prepaid_interest_days: int,
    monthly_insurance: Decimal,
    prepaid_insurance_months: int,
    monthly_tax: Decimal,
    prepaid_tax_months: int,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Returns `(prepaid_interest, prepaid_insurance, prepaid_taxes, total_prepaids)`."""
    prepaid_interest = pi / Decimal("30") * Decimal(prepaid_interest_days)
    prepaid_insurance = monthly_insurance * Decimal(prepaid_insurance_months)
    prepaid_taxes = monthly_tax * Decimal(prepaid_tax_months)
    total = prepaid_interest + prepaid_insurance + prepaid_taxes
    return prepaid_interest, prepaid_insurance, prepaid_taxes, total


def cash_to_close(
    down_payment: Decimal,
    lender_fees: Decimal,
    points_amount: Decimal,
    title_fees: Decimal,
    total_prepaids: Decimal,
    seller_credits: Decimal,
) -> Decimal:
    """`CTC = D + F_lender + points*L + F_title + prepaids - credits`."""
    return down_payment + lender_fees + points_amount + title_fees + total_prepaids - seller_credits


# --- Investment: qualifying rent, DSCR, cashflow, cap rate --------------------


def str_gross_monthly_revenue_amount(str_gross_annual_revenue: Decimal) -> Decimal:
    """`str_gross_annual_revenue / 12` -- the pre-expense-ratio monthly figure.

    Exposed as its own field on `QuoteComputation` (`str_gross_monthly_revenue`)
    so consumers displaying both the gross and net STR figures (e.g. CQ-021's
    report builder) never divide `ScenarioInputs.str_gross_annual_revenue`
    themselves outside the engine."""
    return str_gross_annual_revenue / Decimal("12")


def underwritten_str_rent(str_gross_annual_revenue: Decimal, str_expense_ratio: Decimal) -> Decimal:
    """`gross_monthly_str_revenue x (1 - str_expense_ratio)`, `gross_monthly = annual / 12`."""
    gross_monthly = str_gross_monthly_revenue_amount(str_gross_annual_revenue)
    return gross_monthly * (Decimal("1") - str_expense_ratio)


def dscr_ratio(qualifying_rent: Decimal, total_payment: Decimal) -> Decimal:
    """Unrounded `qualifying_rent / total_monthly_payment`. Round only at output."""
    return qualifying_rent / total_payment


def bucket_for_dscr(dscr: Decimal) -> DSCRBucket:
    """Classifies the *unrounded* DSCR value, not the 2dp display value."""
    if dscr < Decimal("1.00"):
        return DSCRBucket.BELOW_1_00
    if dscr < Decimal("1.25"):
        return DSCRBucket.ONE_TO_1_25
    return DSCRBucket.GE_1_25


def monthly_cashflow_amount(qualifying_rent: Decimal, total_payment: Decimal) -> Decimal:
    return qualifying_rent - total_payment


def break_even_rent_ltr(total_payment: Decimal, target_dscr: Decimal) -> Decimal:
    return total_payment * target_dscr


def str_annual_rent_target(total_payment: Decimal, str_expense_ratio: Decimal) -> Decimal:
    """`total_monthly_payment * 12 / (1 - str_expense_ratio)`.

    Derived from `config.str_expense_ratio` (spec.md, revised) rather than a
    hardcoded `0.80`, so a reconfigured expense ratio moves this formula too.
    At the default `str_expense_ratio = 0.20` this is `/ 0.80`, matching the
    pinned golden value.
    """
    return total_payment * Decimal("12") / (Decimal("1") - str_expense_ratio)


def cap_rate_pct(
    qualifying_rent: Decimal, purchase_price: Decimal, cap_rate_multiplier: Decimal
) -> Decimal:
    """`qualifying_rent * 12 * multiplier / purchase_price`, as a percent (e.g. `6.42`)."""
    return qualifying_rent * Decimal("12") * cap_rate_multiplier / purchase_price * Decimal("100")


# --- Cost segregation ----------------------------------------------------------


def cost_segregation(
    purchase_price: Decimal,
    land_allocation_pct: Decimal,
    accelerated_property_pct: Decimal,
    bonus_depreciation_pct: Decimal,
    investor_marginal_tax_rate: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Returns `(land_value_allocation, depreciable_building_basis,
    accelerated_basis_amount, year_one_tax_deduction, year_one_tax_savings)`,
    all unrounded.

    `B = (1 - land_allocation_pct) * P`, `A = accelerated_property_pct * B`,
    `Ded_1 = A * bonus% + (B - A) / 27.5`, `Savings_1 = Ded_1 * marginal_rate`.
    """
    land_value_allocation = purchase_price * land_allocation_pct
    building_basis = purchase_price * (Decimal("1") - land_allocation_pct)
    accelerated_basis = accelerated_property_pct * building_basis
    year_one_deduction = accelerated_basis * bonus_depreciation_pct + (
        building_basis - accelerated_basis
    ) / Decimal("27.5")
    year_one_savings = year_one_deduction * investor_marginal_tax_rate
    return (
        land_value_allocation,
        building_basis,
        accelerated_basis,
        year_one_deduction,
        year_one_savings,
    )


def monthly_cashflow_incl_tax(monthly_cashflow: Decimal, year_one_tax_savings: Decimal) -> Decimal:
    return monthly_cashflow + year_one_tax_savings / Decimal("12")


# --- Property matches (CQ-023) --------------------------------------------------
# Kept in its own block, at the end of the file, on purpose: CQ-017 (pricing
# panel) also adds a public quote_engine function in this same PR window and
# both items were told to expect an easy merge conflict here -- a dedicated
# section, appended rather than interleaved among the existing ones, keeps
# each item's diff a clean append instead of touching shared lines.

_MATCH_FLOOR_MULTIPLIER = Decimal("0.70")
_MATCH_CEILING_MULTIPLIER = Decimal("1.00")


def match_floor_price(approved_purchase_price: Decimal) -> Decimal:
    """data-field-catalog.md §11 `match_floor_price`: `approved_purchase_price
    x 0.70`, rounded to cents like every other money value this module
    produces. **Hard floor** -- a listing priced below this is never a
    match, whatever else about it fits (buy-box, strategy)."""
    return _round_currency(approved_purchase_price * _MATCH_FLOOR_MULTIPLIER)


def match_ceiling_price(approved_purchase_price: Decimal) -> Decimal:
    """data-field-catalog.md §11 `match_ceiling_price`: `approved_purchase_price
    x 1.00`. **Hard ceiling** -- never show the borrower a home priced above
    what they're approved for."""
    return _round_currency(approved_purchase_price * _MATCH_CEILING_MULTIPLIER)


# --- Orchestration -------------------------------------------------------------


def compute_quote(inputs: ScenarioInputs, config: ConfigSnapshot) -> QuoteComputation:
    """Turns a scenario's inputs into every money number Clear Quote shows.

    Runs the full calculation chain in unrounded Decimal and rounds exactly
    once per field when populating `QuoteComputation`. Investment-only fields
    stay `None` for `PRIMARY` scenarios.
    """
    loan = loan_amount(inputs.purchase_price, inputs.down_payment_pct)
    ltv = ltv_pct(inputs.down_payment_pct)

    if inputs.strategy is StrategyType.PRIMARY and ltv > _MAX_PRIMARY_LTV:
        raise LtvOutOfRangeError(
            f"LTV {ltv * Decimal('100')}% exceeds the conventional financing maximum of "
            f"{_MAX_PRIMARY_LTV * Decimal('100')}% for a PRIMARY scenario."
        )

    pi = principal_and_interest(loan, inputs.note_rate, inputs.term_months)
    tax = monthly_tax_amount(inputs.purchase_price, inputs.property_tax_annual_rate)
    insurance = monthly_insurance_amount(inputs.purchase_price, inputs.insurance_annual_rate)
    mi = monthly_mi_amount(loan, ltv, inputs.fico, inputs.strategy, config)
    payment = total_monthly_payment(pi, tax, insurance, mi, inputs.hoa_monthly)

    down_payment = inputs.purchase_price * inputs.down_payment_pct
    lender_fees = config.lender_processing_fee + config.lender_underwriting_fee
    points_amount = discount_points_amount(inputs.discount_points_pct, loan)
    title_fees = title_fees_amount(inputs.purchase_price, config.title_rate_pct)
    prepaid_interest, prepaid_insurance, prepaid_taxes, total_prepaids = total_prepaids_amount(
        pi,
        config.prepaid_interest_days,
        insurance,
        config.prepaid_insurance_months,
        tax,
        config.prepaid_tax_months,
    )
    total_closing_costs = lender_fees + points_amount + title_fees + total_prepaids
    ctc = cash_to_close(
        down_payment, lender_fees, points_amount, title_fees, total_prepaids, inputs.seller_credits
    )

    rounded_loan_amount = _round_currency(loan)
    rounded_down_payment = _round_currency(down_payment)
    rounded_ltv_pct = _round_ltv(ltv)
    rounded_pi = _round_currency(pi)
    rounded_tax = _round_currency(tax)
    rounded_insurance = _round_currency(insurance)
    rounded_mi = _round_currency(mi) if mi is not None else None
    rounded_hoa = _round_currency(inputs.hoa_monthly)
    rounded_payment = _round_currency(payment)
    rounded_points = _round_currency(points_amount)
    rounded_lender_fees = _round_currency(lender_fees)
    rounded_title_fees = _round_currency(title_fees)
    rounded_prepaid_interest = _round_currency(prepaid_interest)
    rounded_prepaid_insurance = _round_currency(prepaid_insurance)
    rounded_prepaid_taxes = _round_currency(prepaid_taxes)
    rounded_total_prepaids = _round_currency(total_prepaids)
    rounded_total_closing_costs = _round_currency(total_closing_costs)
    rounded_ctc = _round_currency(ctc)

    if inputs.strategy is StrategyType.PRIMARY:
        return QuoteComputation(
            loan_amount=rounded_loan_amount,
            down_payment_amount=rounded_down_payment,
            ltv_pct=rounded_ltv_pct,
            monthly_pi=rounded_pi,
            monthly_tax=rounded_tax,
            monthly_insurance=rounded_insurance,
            monthly_mi=rounded_mi,
            monthly_hoa=rounded_hoa,
            total_monthly_payment=rounded_payment,
            discount_points_amount=rounded_points,
            lender_fees=rounded_lender_fees,
            title_fees=rounded_title_fees,
            prepaid_interest=rounded_prepaid_interest,
            prepaid_insurance=rounded_prepaid_insurance,
            prepaid_taxes=rounded_prepaid_taxes,
            total_prepaids=rounded_total_prepaids,
            total_closing_costs=rounded_total_closing_costs,
            cash_to_close=rounded_ctc,
            config_snapshot=config,
        )

    rounded_str_gross_monthly_revenue: Decimal | None = None
    if inputs.strategy is StrategyType.LTR:
        assert inputs.market_rent_ltr is not None  # enforced by ScenarioInputs.__post_init__
        qualifying_rent = inputs.market_rent_ltr
        underwritten_str: Decimal | None = None
    else:  # STR
        assert inputs.str_gross_annual_revenue is not None
        underwritten_str = underwritten_str_rent(
            inputs.str_gross_annual_revenue, config.str_expense_ratio
        )
        qualifying_rent = underwritten_str
        rounded_str_gross_monthly_revenue = _round_currency(
            str_gross_monthly_revenue_amount(inputs.str_gross_annual_revenue)
        )

    dscr = dscr_ratio(qualifying_rent, payment)
    bucket = bucket_for_dscr(dscr)
    cashflow = monthly_cashflow_amount(qualifying_rent, payment)
    annual_cashflow = cashflow * Decimal("12")
    target_dscr = inputs.target_dscr if inputs.target_dscr is not None else config.target_dscr
    break_even = break_even_rent_ltr(payment, target_dscr)
    str_target = str_annual_rent_target(payment, config.str_expense_ratio)
    cap_rate = cap_rate_pct(qualifying_rent, inputs.purchase_price, config.cap_rate_multiplier)

    bonus_pct = (
        inputs.bonus_depreciation_pct
        if inputs.bonus_depreciation_pct is not None
        else config.bonus_depreciation_pct
    )
    marginal_rate = (
        inputs.investor_marginal_tax_rate
        if inputs.investor_marginal_tax_rate is not None
        else config.investor_marginal_tax_rate
    )
    land_value, building_basis, accelerated_basis, year_one_deduction, year_one_savings = (
        cost_segregation(
            inputs.purchase_price,
            config.land_allocation_pct,
            config.accelerated_property_pct,
            bonus_pct,
            marginal_rate,
        )
    )
    cashflow_incl_tax = monthly_cashflow_incl_tax(cashflow, year_one_savings)

    return QuoteComputation(
        loan_amount=rounded_loan_amount,
        down_payment_amount=rounded_down_payment,
        ltv_pct=rounded_ltv_pct,
        monthly_pi=rounded_pi,
        monthly_tax=rounded_tax,
        monthly_insurance=rounded_insurance,
        monthly_mi=rounded_mi,
        monthly_hoa=rounded_hoa,
        total_monthly_payment=rounded_payment,
        discount_points_amount=rounded_points,
        lender_fees=rounded_lender_fees,
        title_fees=rounded_title_fees,
        prepaid_interest=rounded_prepaid_interest,
        prepaid_insurance=rounded_prepaid_insurance,
        prepaid_taxes=rounded_prepaid_taxes,
        total_prepaids=rounded_total_prepaids,
        total_closing_costs=rounded_total_closing_costs,
        cash_to_close=rounded_ctc,
        config_snapshot=config,
        qualifying_rent=_round_currency(qualifying_rent),
        underwritten_str_rent=(
            _round_currency(underwritten_str) if underwritten_str is not None else None
        ),
        str_gross_monthly_revenue=rounded_str_gross_monthly_revenue,
        dscr_ratio=_round_2dp(dscr),
        dscr_bucket=bucket,
        monthly_cashflow=_round_currency(cashflow),
        annual_cashflow=_round_currency(annual_cashflow),
        break_even_rent_ltr=_round_currency(break_even),
        str_annual_rent_target=_round_currency(str_target),
        cap_rate_pct=_round_2dp(cap_rate),
        land_value_allocation=_round_currency(land_value),
        depreciable_building_basis=_round_currency(building_basis),
        accelerated_basis_amount=_round_currency(accelerated_basis),
        year_one_tax_deduction=_round_currency(year_one_deduction),
        year_one_tax_savings=_round_currency(year_one_savings),
        monthly_cashflow_incl_tax=_round_currency(cashflow_incl_tax),
    )
