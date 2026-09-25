"""CQ-019: the pre-approval letter's verified-assets threshold."""

from decimal import Decimal

from app.features.pricing.engine.quote_engine import verified_assets_floor


def test_verified_assets_floor_sums_and_floors_to_thousands() -> None:
    assert verified_assets_floor([Decimal("100000.00"), Decimal("35999.99")]) == Decimal("135000")
    assert verified_assets_floor([Decimal("80000.00")]) == Decimal("80000")
    assert verified_assets_floor([Decimal("999.99")]) == Decimal("0")
    assert verified_assets_floor([]) == Decimal("0")
