"""AC1/AC8.

Full AC1 ("every dollar/percent/rate value attached to a persona traces to
`quote_engine` output") is a Phase B claim -- in Phase A there is no priced
`Quote` row attached to any persona yet (CQ-013's `auto_price` isn't merged;
see `seed/pricing_seam.py`). What this file proves instead, honestly, for
Phase A:

1. `test_no_reference_sheet_errors_reproduced` (AC8): the exact
   reference-sheet corrections system-design.md calls out (title at 0.7% of
   price, not the catalog's flawed example; cash to close includes discount
   points, not excludes them like the flawed reference report; `ScenarioInputs`
   structurally cannot mix LTR and STR on one scenario) hold against
   `quote_engine` (CQ-008, already merged) directly -- independent of
   whether CQ-013 has wired persisted quotes yet.
2. `test_marcus_hale_raw_inputs_are_engine_consumable`: Marcus Hale's seeded
   *raw inputs* (persona YAML + provider YAML fixtures -- never a computed
   number) feed `compute_quote` directly and produce a coherent result,
   proving the fixtures are inputs an engine run can consume, not
   hand-typed outputs standing in for one.
"""

from decimal import Decimal

from app.features.pricing.engine.quote_engine import (
    LtvOutOfRangeError,
    cash_to_close,
    compute_quote,
    discount_points_amount,
    title_fees_amount,
)
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from seed.loader import load_persona_fixtures, load_provider_fixture


def test_no_reference_sheet_errors_reproduced() -> None:
    # "Title at 0.7% of $342,000 is $2,394, not $2,100" (system-design.md,
    # data-field-catalog override O8) -- reproduced from the engine's own
    # default config, not typed in.
    config = ConfigSnapshot()
    assert config.title_rate_pct == Decimal("0.007")
    title_fee = title_fees_amount(Decimal("342000"), config.title_rate_pct)
    assert title_fee == Decimal("2394.000")

    # "0.750% points that its cash to close excludes" -- our engine's cash
    # to close must include points, not exclude them: a nonzero points_pct
    # measurably changes cash_to_close.
    loan = Decimal("273600")  # 342000 * 0.80
    points_amount = discount_points_amount(Decimal("0.0075"), loan)
    ctc_with_points = cash_to_close(
        down_payment=Decimal("68400"),
        lender_fees=Decimal("1790.00"),
        points_amount=points_amount,
        title_fees=title_fee,
        total_prepaids=Decimal("3000.00"),
        seller_credits=Decimal("0"),
    )
    ctc_without_points = cash_to_close(
        down_payment=Decimal("68400"),
        lender_fees=Decimal("1790.00"),
        points_amount=Decimal("0"),
        title_fees=title_fee,
        total_prepaids=Decimal("3000.00"),
        seller_credits=Decimal("0"),
    )
    assert ctc_with_points - ctc_without_points == points_amount
    assert points_amount != Decimal("0")

    # "The reference report mixes LTR (+$196) and STR (-$264) cashflow for
    # one property" -- our engine structurally forbids this: a single
    # ScenarioInputs can only carry one of market_rent_ltr /
    # str_gross_annual_revenue, enforced by its own validator.
    try:
        ScenarioInputs(
            purchase_price=Decimal("300000"),
            down_payment_pct=Decimal("0.25"),
            note_rate=Decimal("0.0725"),
            strategy=StrategyType.LTR,
            fico=720,
            property_tax_annual_rate=Decimal("0.01"),
            insurance_annual_rate=Decimal("0.005"),
            market_rent_ltr=Decimal("2200"),
            str_gross_annual_revenue=Decimal("48000"),  # both set -- must reject
        )
        raise AssertionError("expected ValueError for mixed LTR/STR inputs")
    except ValueError:
        pass


def test_marcus_hale_raw_inputs_are_engine_consumable() -> None:
    personas = {p["key"]: p for p in load_persona_fixtures()}
    marcus = personas["marcus_hale"]
    assert marcus["strategy"] == "str"

    tax_rows = {
        (row["county"], row["state"]): row for row in load_provider_fixture("tax_rates.yaml")
    }
    tax_row = tax_rows[(marcus["market"]["county"], marcus["market"]["state"])]

    str_rows = {(row["zip"], row["beds"]): row for row in load_provider_fixture("str_revenue.yaml")}
    # Keyed on Property.number_of_units (always 1, single_family) -- not the
    # persona table's own "Beds" column; see CQ-013's enrichment/service.py
    # _enrich_str_revenue, which looks these tables up by property attribute.
    str_row = str_rows[(marcus["market"]["zip"], 1)]

    rate_sheet = load_provider_fixture("rate_sheet.yaml")
    dscr_str_row = next(r for r in rate_sheet if r["program"] == "dscr" and r.get("str_only"))

    inputs = ScenarioInputs(
        purchase_price=Decimal(str(marcus["purchase_price"])),
        down_payment_pct=Decimal(str(marcus["down_payment_pct"])),
        note_rate=Decimal(str(dscr_str_row["base_rate"])) / Decimal("100"),
        strategy=StrategyType.STR,
        fico=marcus["fico"],
        property_tax_annual_rate=Decimal(str(tax_row["annual_rate_pct"])) / Decimal("100"),
        insurance_annual_rate=Decimal("0.005"),
        str_gross_annual_revenue=Decimal(str(str_row["annual_revenue"])),
    )
    config = ConfigSnapshot()

    result = compute_quote(inputs, config)

    price = Decimal(str(marcus["purchase_price"]))
    down_pct = Decimal(str(marcus["down_payment_pct"]))
    assert result.loan_amount == (price * (Decimal("1") - down_pct)).quantize(Decimal("0.01"))
    assert result.qualifying_rent is not None
    assert result.dscr_ratio is not None
    assert result.title_fees == (price * config.title_rate_pct).quantize(Decimal("0.01"))
    # PRIMARY-only fields stay None on this investment scenario.
    assert result.monthly_mi is None


def test_primary_ltv_over_97pct_is_rejected_not_silently_priced() -> None:
    """A PRIMARY scenario's LTV can never silently exceed the conventional
    financing maximum -- another way a seed value could contradict the
    engine's own guardrails if hand-typed instead of engine-derived."""
    inputs = ScenarioInputs(
        purchase_price=Decimal("260000"),
        down_payment_pct=Decimal("0.01"),
        note_rate=Decimal("0.065"),
        strategy=StrategyType.PRIMARY,
        fico=730,
        property_tax_annual_rate=Decimal("0.0085"),
        insurance_annual_rate=Decimal("0.005"),
    )
    try:
        compute_quote(inputs, ConfigSnapshot())
        raise AssertionError("expected LtvOutOfRangeError")
    except LtvOutOfRangeError:
        pass
