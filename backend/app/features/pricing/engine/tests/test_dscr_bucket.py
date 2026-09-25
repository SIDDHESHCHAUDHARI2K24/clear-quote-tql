"""AC11 — DSCR bucket boundaries. Classifies the unrounded value."""

from decimal import Decimal

import pytest

from app.features.pricing.engine.quote_engine import bucket_for_dscr
from app.features.pricing.engine.types import DSCRBucket


@pytest.mark.parametrize(
    ("dscr", "expected"),
    [
        (Decimal("0.99"), DSCRBucket.BELOW_1_00),
        (Decimal("1.00"), DSCRBucket.ONE_TO_1_25),
        (Decimal("1.24"), DSCRBucket.ONE_TO_1_25),
        (Decimal("1.25"), DSCRBucket.GE_1_25),
    ],
)
def test_dscr_bucket_boundaries(dscr: Decimal, expected: DSCRBucket) -> None:
    assert bucket_for_dscr(dscr) is expected


def test_dscr_bucket_classifies_unrounded_value() -> None:
    # 1.249 rounds to 1.25 at 2dp, but must still classify as ONE_TO_1_25
    # because bucket_for_dscr reads the unrounded value.
    assert bucket_for_dscr(Decimal("1.249")) is DSCRBucket.ONE_TO_1_25
