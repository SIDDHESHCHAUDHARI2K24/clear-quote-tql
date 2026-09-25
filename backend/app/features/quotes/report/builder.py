"""`build_report_view_model` -- the pure function CQ-019 and CQ-022 both call.

No I/O, no DB (see inputs.py). Every money/rate/percent value already lives
as a rounded `Decimal` on `QuoteComputation` (the engine rounds exactly once,
per quote_engine.py's own rounding rule, and now also computes
`down_payment_amount`/`str_gross_monthly_revenue` directly -- CQ-021 review
M1); this module's only job is to *format* those decimals into the strings
`ReportViewModel` carries and to group them under the headings spec.md pins
(hero, breakdown, cashflow, cost_seg). It performs no arithmetic of its own
-- every value below is either passed straight through, or scaled/rounded
for *display only* (percent scaling, whole-dollar rounding of an
already-engine-computed value), never combined with another value to derive
a new financial fact.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.features.pricing.engine.types import QuoteComputation, StrategyType

from .inputs import ReportInputs, ReportMatchInput, ReportOptionInput
from .schemas import (
    Breakdown,
    BreakdownLine,
    CashflowTable,
    CostSegTable,
    HeroNumbers,
    ReportDisclosures,
    ReportHeader,
    ReportLo,
    ReportMatch,
    ReportOption,
    ReportRecommendation,
    ReportStrategy,
    ReportViewModel,
)

_CENT = Decimal("0.01")
_WHOLE_DOLLAR = Decimal("1")
_PCT_3DP = Decimal("0.001")
_PCT_2DP = Decimal("0.01")

_CORE_DISCLAIMER = (
    "This is not a commitment to lend. Rates, payments and closing costs are "
    "estimates based on the information available today and are subject to "
    "change once your file is fully underwritten. This is not a Loan Estimate."
)
_INVESTMENT_DISCLAIMER = (
    "Rental income and cashflow figures are estimates based on third-party "
    "market data (RentCast/AirDNA) and are not a guarantee of actual "
    "performance."
)
_TAX_DISCLAIMER = "Estimate only, not tax advice. Consult your tax professional."

_PROPERTY_TBD_LABEL = "Property to be determined"


def _money(value: Decimal) -> str:
    return str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _rate_pct(fraction: Decimal) -> str:
    """Fraction (e.g. `0.075`) -> 3dp percent string (e.g. `"7.500"`)."""
    return str((fraction * Decimal("100")).quantize(_PCT_3DP, rounding=ROUND_HALF_UP))


def _pct_2dp(fraction: Decimal) -> str:
    """Fraction (e.g. `0.20`) -> 2dp percent string (e.g. `"20.00"`)."""
    return str((fraction * Decimal("100")).quantize(_PCT_2DP, rounding=ROUND_HALF_UP))


def _to_report_strategy(strategy: StrategyType) -> ReportStrategy:
    return ReportStrategy[strategy.name]


def _gross_rent_monthly(strategy: StrategyType, computation: QuoteComputation) -> Decimal:
    """The pre-expense-ratio monthly rent/revenue figure for the cashflow
    table's "gross" row. For LTR this is exactly `qualifying_rent` (100% of
    market rent, no expense ratio applied -- system-design.md's "Qualifying
    rent" formula). For STR it is `computation.str_gross_monthly_revenue`,
    computed by the engine (CQ-021 review M1) -- this function only selects
    which already-engine-produced field to read, it performs no arithmetic."""
    if strategy is StrategyType.LTR:
        assert computation.qualifying_rent is not None
        return computation.qualifying_rent
    assert computation.str_gross_monthly_revenue is not None
    return computation.str_gross_monthly_revenue


def _build_hero(strategy: StrategyType, computation: QuoteComputation) -> HeroNumbers:
    monthly_payment = _money(computation.total_monthly_payment)
    cash_to_close = _money(computation.cash_to_close)

    if strategy is StrategyType.PRIMARY:
        return HeroNumbers(
            monthly_payment=monthly_payment,
            cash_to_close=cash_to_close,
            loan_amount=_money(computation.loan_amount),
            monthly_cashflow=None,
            year1_tax_savings=None,
            year1_tax_savings_monthly=None,
        )

    assert computation.monthly_cashflow is not None
    assert computation.year_one_tax_savings is not None
    monthly_approx = (computation.year_one_tax_savings / Decimal("12")).quantize(
        _WHOLE_DOLLAR, rounding=ROUND_HALF_UP
    )
    return HeroNumbers(
        monthly_payment=monthly_payment,
        cash_to_close=cash_to_close,
        loan_amount=None,
        monthly_cashflow=_money(computation.monthly_cashflow),
        year1_tax_savings=_money(computation.year_one_tax_savings),
        year1_tax_savings_monthly=str(monthly_approx),
    )


def _build_breakdown(computation: QuoteComputation) -> Breakdown:
    c = computation
    payment_lines = [
        BreakdownLine(label="Principal & interest", amount=_money(c.monthly_pi)),
        BreakdownLine(label="Property taxes", amount=_money(c.monthly_tax)),
        BreakdownLine(label="Homeowners insurance", amount=_money(c.monthly_insurance)),
    ]
    if c.monthly_mi is not None:
        payment_lines.append(BreakdownLine(label="Mortgage insurance", amount=_money(c.monthly_mi)))
    if c.monthly_hoa != Decimal("0"):
        payment_lines.append(BreakdownLine(label="HOA", amount=_money(c.monthly_hoa)))

    points_label = (
        "Discount points" if c.discount_points_amount >= Decimal("0") else "Points credit"
    )
    cash_to_close_lines = [
        BreakdownLine(label="Down payment", amount=_money(c.down_payment_amount)),
        BreakdownLine(label="Lender fees", amount=_money(c.lender_fees)),
        BreakdownLine(label=points_label, amount=_money(c.discount_points_amount)),
        BreakdownLine(label="Title & escrow", amount=_money(c.title_fees)),
        BreakdownLine(label="Prepaid interest", amount=_money(c.prepaid_interest)),
        BreakdownLine(label="Prepaid insurance", amount=_money(c.prepaid_insurance)),
        BreakdownLine(label="Prepaid taxes", amount=_money(c.prepaid_taxes)),
    ]
    return Breakdown(
        payment_lines=payment_lines,
        payment_total=_money(c.total_monthly_payment),
        cash_to_close_lines=cash_to_close_lines,
        cash_to_close_total=_money(c.cash_to_close),
    )


def _build_cashflow(strategy: StrategyType, computation: QuoteComputation) -> CashflowTable:
    c = computation
    assert c.qualifying_rent is not None
    assert c.dscr_ratio is not None
    assert c.monthly_cashflow is not None
    assert c.annual_cashflow is not None
    assert c.cap_rate_pct is not None
    assert c.monthly_cashflow_incl_tax is not None

    gross = _gross_rent_monthly(strategy, c)
    is_str = strategy is StrategyType.STR
    return CashflowTable(
        rent_label="Gross STR revenue" if is_str else "Market rent (LTR)",
        gross_amount=_money(gross),
        expense_ratio=_pct_2dp(c.config_snapshot.str_expense_ratio) if is_str else None,
        qualifying_rent=_money(c.qualifying_rent),
        pitia=_money(c.total_monthly_payment),
        monthly_cashflow=_money(c.monthly_cashflow),
        annual_cashflow=_money(c.annual_cashflow),
        dscr=str(c.dscr_ratio),
        cap_rate_pct=str(c.cap_rate_pct),
        monthly_cashflow_incl_tax=_money(c.monthly_cashflow_incl_tax),
    )


def _build_cost_seg(purchase_price: Decimal, computation: QuoteComputation) -> CostSegTable:
    c = computation
    assert c.land_value_allocation is not None
    assert c.depreciable_building_basis is not None
    assert c.accelerated_basis_amount is not None
    assert c.year_one_tax_deduction is not None
    assert c.year_one_tax_savings is not None

    return CostSegTable(
        purchase_price=_money(purchase_price),
        land_allocation_pct=_pct_2dp(c.config_snapshot.land_allocation_pct),
        land_value_allocation=_money(c.land_value_allocation),
        depreciable_building_basis=_money(c.depreciable_building_basis),
        accelerated_property_pct=_pct_2dp(c.config_snapshot.accelerated_property_pct),
        accelerated_basis_amount=_money(c.accelerated_basis_amount),
        bonus_depreciation_pct=_pct_2dp(c.config_snapshot.bonus_depreciation_pct),
        year_one_tax_deduction=_money(c.year_one_tax_deduction),
        investor_marginal_tax_rate=_pct_2dp(c.config_snapshot.investor_marginal_tax_rate),
        year_one_tax_savings=_money(c.year_one_tax_savings),
    )


def _build_option(
    strategy: StrategyType, purchase_price: Decimal, option: ReportOptionInput
) -> ReportOption:
    c = option.computation
    is_primary = strategy is StrategyType.PRIMARY
    return ReportOption(
        quote_id=option.quote_id,
        label=option.label,
        recommended=option.recommended,
        rate=_rate_pct(option.note_rate),
        points_pct=_rate_pct(option.discount_points_pct),
        points_amount=_money(c.discount_points_amount),
        down_payment_pct=_pct_2dp(option.down_payment_pct),
        prepay_label=option.prepay_label,
        hero=_build_hero(strategy, c),
        breakdown=_build_breakdown(c),
        cashflow=None if is_primary else _build_cashflow(strategy, c),
        cost_seg=None if is_primary else _build_cost_seg(purchase_price, c),
    )


def _build_match(match: ReportMatchInput) -> ReportMatch:
    return ReportMatch(
        matched_property_id=match.matched_property_id,
        property_image_url=match.property_image_url,
        property_address=match.property_address,
        bed_bath_sqft=match.bed_bath_sqft,
        deal_grade_badge=match.deal_grade_badge,
        property_tagline=match.property_tagline,
        price=_money(match.price),
        total_monthly_payment=_money(match.total_monthly_payment),
        rent_estimate=_money(match.rent_estimate) if match.rent_estimate is not None else None,
        rent_label=match.rent_label,
        monthly_cashflow=(
            _money(match.monthly_cashflow) if match.monthly_cashflow is not None else None
        ),
        cash_to_close=_money(match.cash_to_close),
        cap_rate_pct=str(match.cap_rate_pct) if match.cap_rate_pct is not None else None,
        year1_tax_savings=(
            _money(match.year1_tax_savings) if match.year1_tax_savings is not None else None
        ),
    )


def _build_disclosures(strategy: StrategyType) -> ReportDisclosures:
    is_primary = strategy is StrategyType.PRIMARY
    return ReportDisclosures(
        core=_CORE_DISCLAIMER,
        investment=None if is_primary else _INVESTMENT_DISCLAIMER,
        tax=None if is_primary else _TAX_DISCLAIMER,
    )


def build_report_view_model(inputs: ReportInputs) -> ReportViewModel:
    """Pure: every field is either passed straight through or formatted as a
    decimal/percent string from an already-engine-computed `QuoteComputation`
    value (see `_gross_rent_monthly` for the one field-selection helper). No
    DB, no network, no engine recomputation -- `ReportOptionInput.computation`
    is always an already-computed `QuoteComputation`."""
    header = ReportHeader(
        first_name=inputs.first_name,
        property_label=inputs.property_label or _PROPERTY_TBD_LABEL,
        purchase_price=_money(inputs.purchase_price),
        prepared_at=inputs.prepared_at.isoformat(),
        rates_as_of=inputs.rates_as_of.isoformat(),
        expires_at=inputs.expires_at.isoformat() if inputs.expires_at else None,
        expired=inputs.expired,
        superseded=inputs.superseded,
    )

    # Recommended option(s) first, stable otherwise (spec.md: "options[]
    # (recommended first)").
    ordered_options = sorted(inputs.options, key=lambda o: not o.recommended)
    options = [_build_option(inputs.strategy, inputs.purchase_price, o) for o in ordered_options]

    return ReportViewModel(
        header=header,
        strategy=_to_report_strategy(inputs.strategy),
        options=options,
        recommendation=ReportRecommendation(
            text=inputs.recommendation_text, lo_note=inputs.lo_note
        ),
        matches=[_build_match(m) for m in inputs.matches],
        disclosures=_build_disclosures(inputs.strategy),
        lo=ReportLo(
            name=inputs.lo_name,
            title=inputs.lo_title,
            nmls=inputs.lo_nmls,
            phone=inputs.lo_phone,
            email=inputs.lo_email,
        ),
    )
