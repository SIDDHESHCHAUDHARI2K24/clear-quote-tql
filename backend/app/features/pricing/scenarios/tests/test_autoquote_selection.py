"""AC7: `select_par_and_buydown` picks the correct par (closest to 0 points)
and buydown (lowest rate, <= 1.00 point) from a fixture rate sheet, and
returns `None` buydown when no row qualifies.
"""

from decimal import Decimal

import pytest

from app.features.pricing.scenarios.service import select_par_and_buydown
from app.integrations.pricing.schemas import PricedProductDTO


def _row(
    investor_name: str,
    note_rate: str,
    discount_points_pct: str,
    is_par_rate: bool = False,
) -> PricedProductDTO:
    return PricedProductDTO(
        investor_name=investor_name,
        product_name="Investor Solutions DSCR 30 Yr Fixed",
        lock_period_days=30,
        note_rate=Decimal(note_rate),
        price_pct=Decimal("100.000"),
        discount_points_pct=Decimal(discount_points_pct),
        discount_points_amount=Decimal("0"),
        is_par_rate=is_par_rate,
        is_buydown_rate=False,
    )


def test_selects_the_marked_par_row_and_the_cheapest_qualifying_buydown() -> None:
    rows = [
        _row("Verus", "7.875", "-0.500"),
        _row("Deephaven", "7.500", "0.000", is_par_rate=True),
        _row("LendSure", "7.250", "0.0080"),  # 0.80 point -> qualifies
        _row("Angel Oak", "7.125", "0.0150"),  # 1.50 points -> too many
    ]

    par, buydown = select_par_and_buydown(rows)

    assert par.investor_name == "Deephaven"
    assert buydown is not None
    assert buydown.investor_name == "LendSure"
    assert buydown.note_rate == Decimal("7.250")


def test_no_qualifying_buydown_row_returns_none() -> None:
    rows = [
        _row("Verus", "7.875", "-0.500"),
        _row("Deephaven", "7.500", "0.000", is_par_rate=True),
        _row("Angel Oak", "7.125", "0.0150"),  # 1.50 points -> too many
    ]

    par, buydown = select_par_and_buydown(rows)

    assert par.investor_name == "Deephaven"
    assert buydown is None


def test_par_tie_break_by_min_abs_points_then_rate_then_investor_name() -> None:
    # Two rows tied on `is_par_rate=True` with the same abs(points) and
    # note_rate -- deterministic tie-break falls to investor_name.
    rows = [
        _row("Zenith", "7.500", "0.000", is_par_rate=True),
        _row("Acme", "7.500", "0.000", is_par_rate=True),
    ]

    par, _buydown = select_par_and_buydown(rows)

    assert par.investor_name == "Acme"


def test_par_tie_break_prefers_lower_abs_points_over_lower_rate() -> None:
    rows = [
        _row("Acme", "7.250", "0.0020", is_par_rate=True),
        _row("Zenith", "7.500", "0.0010", is_par_rate=True),
    ]

    par, _buydown = select_par_and_buydown(rows)

    assert par.investor_name == "Zenith"


def test_no_par_row_raises() -> None:
    rows = [_row("Verus", "7.875", "-0.500")]

    with pytest.raises(ValueError):
        select_par_and_buydown(rows)


def test_buydown_at_exactly_one_point_qualifies() -> None:
    rows = [
        _row("Deephaven", "7.500", "0.000", is_par_rate=True),
        _row("LendSure", "7.125", "0.0100"),  # exactly 1.00 point -> qualifies
    ]

    _par, buydown = select_par_and_buydown(rows)

    assert buydown is not None
    assert buydown.investor_name == "LendSure"
