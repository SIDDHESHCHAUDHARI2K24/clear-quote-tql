"""P&I amortization formula — supplementary coverage.

The binding golden P&I cases (AC2, AC3) live in `test_golden.py` per the
spec's acceptance/test-plan mapping. This file covers additional formula
edge cases: a well-known reference value and the zero-rate boundary.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.features.pricing.engine.quote_engine import principal_and_interest

_CENT = Decimal("0.01")


def test_pi_100000_at_6_percent_reference_value() -> None:
    # Widely-cited reference: $100,000 at 6.000%, 30y -> $599.55.
    pi = principal_and_interest(Decimal("100000"), Decimal("0.06"), 360)
    assert pi.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("599.55")


def test_pi_zero_rate_is_straight_line() -> None:
    # r == 0 must not divide by zero; P&I degenerates to loan / n.
    pi = principal_and_interest(Decimal("120000"), Decimal("0"), 360)
    assert pi.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("333.33")


def test_pi_scales_with_loan_amount() -> None:
    # P&I is linear in the loan amount; compare at cent precision since the
    # unrounded Decimal context can differ in its last guard digits between
    # the two independent computations.
    small = principal_and_interest(Decimal("100000"), Decimal("0.07"), 360)
    double = principal_and_interest(Decimal("200000"), Decimal("0.07"), 360)
    assert double.quantize(_CENT, rounding=ROUND_HALF_UP) == (small * 2).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )
