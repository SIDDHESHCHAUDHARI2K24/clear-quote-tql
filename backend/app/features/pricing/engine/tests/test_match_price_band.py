"""AC6 (CQ-023 spec.md) -- `match_floor_price`/`match_ceiling_price`: pure
Decimal band-boundary math, data-field-catalog.md §11's `match_floor_price`
(`x 0.70`) / `match_ceiling_price` (`x 1.00`). This is the one place these
two multipliers live -- the service layer (`backend/app/features/matches`)
never re-derives them.
"""

from decimal import Decimal

from app.features.pricing.engine.quote_engine import match_ceiling_price, match_floor_price


def test_price_band_boundaries() -> None:
    approved_price = Decimal("300000.00")

    floor = match_floor_price(approved_price)
    ceiling = match_ceiling_price(approved_price)

    assert floor == Decimal("210000.00")
    assert ceiling == Decimal("300000.00")

    # A listing at exactly 69%/101% is outside the band (spec.md AC6); a
    # listing at exactly 70%/100% is inside it (the "hard floor"/"hard
    # ceiling" are themselves valid prices, not exclusive bounds).
    at_69_pct = approved_price * Decimal("0.69")
    at_70_pct = approved_price * Decimal("0.70")
    at_100_pct = approved_price * Decimal("1.00")
    at_101_pct = approved_price * Decimal("1.01")

    assert at_69_pct < floor
    assert at_70_pct == floor
    assert at_100_pct == ceiling
    assert at_101_pct > ceiling


def test_price_band_rounds_to_cents() -> None:
    # An approved price that doesn't divide evenly at 70% still rounds to
    # a valid 2dp currency value, half-up, like every other money field
    # this module produces.
    approved_price = Decimal("299999.99")
    floor = match_floor_price(approved_price)
    ceiling = match_ceiling_price(approved_price)

    assert floor == Decimal("209999.99")  # 299999.993 -> half-up -> .99
    assert ceiling == Decimal("299999.99")
    assert str(floor).count(".") == 1 and len(str(floor).split(".")[1]) == 2
