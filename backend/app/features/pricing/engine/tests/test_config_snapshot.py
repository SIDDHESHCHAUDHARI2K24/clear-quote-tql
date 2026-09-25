"""AC13 — ConfigSnapshot defaults and immutability."""

import dataclasses
from decimal import Decimal

import pytest

from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType


def test_config_snapshot_defaults() -> None:
    config = ConfigSnapshot()

    assert config.lender_processing_fee == Decimal("995.00")
    assert config.lender_underwriting_fee == Decimal("795.00")
    assert config.lender_processing_fee + config.lender_underwriting_fee == Decimal("1790.00")
    assert config.title_rate_pct == Decimal("0.007")
    assert config.insurance_rate_pct == Decimal("0.005")
    assert config.prepaid_interest_days == 15
    assert config.prepaid_insurance_months == 14
    assert config.prepaid_tax_months == 3
    assert config.str_expense_ratio == Decimal("0.20")
    assert config.cap_rate_multiplier == Decimal("0.75")
    assert config.land_allocation_pct == Decimal("0.20")
    assert config.accelerated_property_pct == Decimal("0.25")
    assert config.bonus_depreciation_pct == Decimal("1.00")
    assert config.investor_marginal_tax_rate == Decimal("0.32")
    assert config.target_dscr == Decimal("1.00")
    assert config.reserves_months_primary == 2
    assert config.reserves_months_investment == 6
    assert len(config.mi_matrix) == 4


def test_config_snapshot_frozen() -> None:
    config = ConfigSnapshot()

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.lender_processing_fee = Decimal("1.00")  # type: ignore[misc]

    # A stored QuoteComputation.config_snapshot must not change when a later,
    # differently-configured ConfigSnapshot is created (old quotes never
    # change when defaults change later).
    original_config = ConfigSnapshot()
    inputs = ScenarioInputs(
        purchase_price=Decimal("225000"),
        down_payment_pct=Decimal("0.20"),
        note_rate=Decimal("0.07125"),
        strategy=StrategyType.PRIMARY,
        fico=760,
        property_tax_annual_rate=Decimal("0.01"),
        insurance_annual_rate=Decimal("0.005"),
    )
    quote = compute_quote(inputs, original_config)

    later_config = ConfigSnapshot(lender_processing_fee=Decimal("1234.56"))

    assert quote.config_snapshot.lender_processing_fee == Decimal("995.00")
    assert later_config.lender_processing_fee == Decimal("1234.56")
    assert quote.config_snapshot is original_config
