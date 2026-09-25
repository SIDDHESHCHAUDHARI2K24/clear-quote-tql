"""AC12 — cash to close formula and discount-point credits."""

from decimal import Decimal

from app.features.pricing.engine.quote_engine import (
    cash_to_close,
    compute_quote,
    discount_points_amount,
    principal_and_interest,
    title_fees_amount,
    total_prepaids_amount,
)
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType


def _inputs(
    *, discount_points_pct: Decimal, seller_credits: Decimal = Decimal("0")
) -> ScenarioInputs:
    return ScenarioInputs(
        purchase_price=Decimal("300000"),
        down_payment_pct=Decimal("0.20"),
        note_rate=Decimal("0.07"),
        strategy=StrategyType.PRIMARY,
        fico=760,
        property_tax_annual_rate=Decimal("0.012"),
        insurance_annual_rate=Decimal("0.005"),
        discount_points_pct=discount_points_pct,
        seller_credits=seller_credits,
    )


def test_cash_to_close_formula() -> None:
    """CTC = D + F_lender + points*L + F_title + prepaids - credits, independently
    recomputed from the same sub-formulas and cross-checked against `compute_quote`."""
    config = ConfigSnapshot()
    inputs = _inputs(discount_points_pct=Decimal("0.00875"))
    quote = compute_quote(inputs, config)

    loan = Decimal("240000")  # 300000 * (1 - 0.20)
    down_payment = Decimal("300000") * Decimal("0.20")
    lender_fees = config.lender_processing_fee + config.lender_underwriting_fee
    points = discount_points_amount(inputs.discount_points_pct, loan)
    title_fees = title_fees_amount(inputs.purchase_price, config.title_rate_pct)
    pi = principal_and_interest(loan, inputs.note_rate, inputs.term_months)
    _, _, _, total_prepaids = total_prepaids_amount(
        pi,
        config.prepaid_interest_days,
        inputs.purchase_price * inputs.insurance_annual_rate / Decimal("12"),
        config.prepaid_insurance_months,
        inputs.purchase_price * inputs.property_tax_annual_rate / Decimal("12"),
        config.prepaid_tax_months,
    )
    expected = cash_to_close(
        down_payment, lender_fees, points, title_fees, total_prepaids, inputs.seller_credits
    )

    assert quote.cash_to_close == expected.quantize(Decimal("0.01"))
    assert quote.discount_points_amount == points.quantize(Decimal("0.01"))
    assert quote.title_fees == Decimal("2100.00")  # 300000 * 0.007
    assert quote.lender_fees == Decimal("1790.00")


def test_cash_to_close_with_credit() -> None:
    """A negative discount_points_pct is a lender credit that reduces CTC by
    exactly the credit amount, all else held equal."""
    config = ConfigSnapshot()
    par_quote = compute_quote(_inputs(discount_points_pct=Decimal("0")), config)
    credit_quote = compute_quote(_inputs(discount_points_pct=Decimal("-0.005")), config)

    loan = Decimal("240000")
    expected_credit_amount = Decimal("-0.005") * loan  # -1200.00

    assert credit_quote.discount_points_amount == expected_credit_amount.quantize(Decimal("0.01"))
    assert credit_quote.discount_points_amount < Decimal("0")
    assert credit_quote.cash_to_close == par_quote.cash_to_close + expected_credit_amount.quantize(
        Decimal("0.01")
    )
    assert credit_quote.cash_to_close < par_quote.cash_to_close
