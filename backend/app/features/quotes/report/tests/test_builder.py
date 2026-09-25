"""Builder tests for CQ-021 acceptance criteria AC1-AC4, AC7 (schema shape).

Each persona's `ReportInputs` is assembled from real `compute_quote` output
(never a hand-typed number), mirroring `seed/tests/test_personas_match_engine.py`'s
own "raw inputs -> engine -> assert" pattern, per spec.md's "seed-independent
fixtures ... built by running quote_engine on their persona inputs."
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.quotes.report.builder import build_report_view_model
from app.features.quotes.report.inputs import ReportInputs, ReportOptionInput


def _marcus_hale_inputs() -> ReportInputs:
    config = ConfigSnapshot()
    purchase_price = Decimal("342000.00")
    down_payment_pct = Decimal("0.20")
    str_gross_annual_revenue = Decimal("24000")

    par = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.075"),
        strategy=StrategyType.STR,
        fico=760,
        property_tax_annual_rate=Decimal("0.0089"),
        insurance_annual_rate=Decimal("0.005"),
        str_gross_annual_revenue=str_gross_annual_revenue,
    )
    buydown = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.06875"),
        strategy=StrategyType.STR,
        fico=760,
        property_tax_annual_rate=Decimal("0.0089"),
        insurance_annual_rate=Decimal("0.005"),
        discount_points_pct=Decimal("0.01"),
        str_gross_annual_revenue=str_gross_annual_revenue,
    )

    return ReportInputs(
        first_name="Marcus",
        property_label="4412 W Gray St, Tampa, FL 33602",
        purchase_price=purchase_price,
        strategy=StrategyType.STR,
        prepared_at=date(2026, 9, 25),
        rates_as_of=date(2026, 9, 25),
        expires_at=date(2026, 10, 16),
        expired=False,
        superseded=False,
        options=[
            ReportOptionInput(
                quote_id="par-quote",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="5-year prepayment penalty",
                computation=compute_quote(par, config),
            ),
            ReportOptionInput(
                quote_id="buydown-quote",
                label="Buydown",
                recommended=False,
                note_rate=buydown.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=buydown.discount_points_pct,
                prepay_label="5-year prepayment penalty",
                computation=compute_quote(buydown, config),
            ),
        ],
        recommendation_text="We recommend the par option for the lowest cash to close.",
        lo_note="Happy to walk through the numbers whenever works for you.",
        lo_name="Jordan Blake",
        lo_title="Loan Officer",
        lo_nmls="NMLS #1933377",
        lo_phone="(813) 555-0100",
        lo_email="jordan.blake@clearquote-demo.test",
    )


def test_view_model_marcus_hale() -> None:
    view_model = build_report_view_model(_marcus_hale_inputs())

    assert view_model.strategy.value == "str"
    assert view_model.header.property_label == "4412 W Gray St, Tampa, FL 33602"

    par_option = next(o for o in view_model.options if o.label == "Par")
    assert par_option.recommended is True
    assert par_option.rate == "7.500"
    assert par_option.breakdown.payment_lines[0].label == "Principal & interest"
    assert par_option.breakdown.payment_lines[0].amount == "1913.05"

    assert par_option.hero.year1_tax_savings == "24275.78"
    assert par_option.hero.year1_tax_savings_monthly == "2023"

    assert par_option.cashflow is not None
    assert par_option.cashflow.rent_label == "Gross STR revenue"
    # Negative -- red in the UI (component-level test), but the value itself
    # is a plain (negative) decimal string here.
    assert Decimal(par_option.cashflow.monthly_cashflow) < Decimal("0")

    # Recommended-first ordering (spec.md).
    assert view_model.options[0].label == "Par"
    assert view_model.options[1].label == "Buydown"


def test_view_model_kathleen_mcreynolds_ltr_tbd() -> None:
    config = ConfigSnapshot()
    purchase_price = Decimal("300000.00")
    down_payment_pct = Decimal("0.25")
    market_rent = Decimal("2250")

    par = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.0725"),
        strategy=StrategyType.LTR,
        fico=720,
        property_tax_annual_rate=Decimal("0.0089"),
        insurance_annual_rate=Decimal("0.005"),
        market_rent_ltr=market_rent,
    )
    inputs = ReportInputs(
        first_name="Kathleen",
        property_label=None,
        purchase_price=purchase_price,
        strategy=StrategyType.LTR,
        prepared_at=date(2026, 9, 25),
        rates_as_of=date(2026, 9, 25),
        expires_at=date(2026, 10, 16),
        expired=False,
        superseded=False,
        options=[
            ReportOptionInput(
                quote_id="par-quote",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="5-year prepayment penalty",
                computation=compute_quote(par, config),
            ),
        ],
        recommendation_text="We recommend the par option.",
        lo_note=None,
        lo_name="Jordan Blake",
        lo_title="Loan Officer",
        lo_nmls="NMLS #1933377",
        lo_phone="(813) 555-0100",
        lo_email="jordan.blake@clearquote-demo.test",
    )

    view_model = build_report_view_model(inputs)

    assert view_model.header.property_label == "Property to be determined"
    assert view_model.strategy.value == "ltr"
    assert view_model.options[0].cashflow is not None
    assert view_model.options[0].cashflow.rent_label == "Market rent (LTR)"
    assert view_model.options[0].cashflow.expense_ratio is None


def test_view_model_priya_nair_primary_has_no_investment_fields() -> None:
    config = ConfigSnapshot()
    purchase_price = Decimal("420000.00")
    down_payment_pct = Decimal("0.20")

    par = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.065"),
        strategy=StrategyType.PRIMARY,
        fico=760,
        property_tax_annual_rate=Decimal("0.0085"),
        insurance_annual_rate=Decimal("0.005"),
    )
    inputs = ReportInputs(
        first_name="Priya",
        property_label="18 Maple Ct, Carmel, IN 46032",
        purchase_price=purchase_price,
        strategy=StrategyType.PRIMARY,
        prepared_at=date(2026, 9, 25),
        rates_as_of=date(2026, 9, 25),
        expires_at=date(2026, 10, 16),
        expired=False,
        superseded=False,
        options=[
            ReportOptionInput(
                quote_id="par-quote",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="No prepayment penalty",
                computation=compute_quote(par, config),
            ),
        ],
        recommendation_text="We recommend the par option.",
        lo_note=None,
        lo_name="Jordan Blake",
        lo_title="Loan Officer",
        lo_nmls="NMLS #1933377",
        lo_phone="(813) 555-0100",
        lo_email="jordan.blake@clearquote-demo.test",
    )

    view_model = build_report_view_model(inputs)
    option = view_model.options[0]

    assert option.cashflow is None
    assert option.cost_seg is None
    assert option.hero.loan_amount is not None
    assert option.hero.monthly_cashflow is None
    assert option.hero.year1_tax_savings is None
    assert view_model.disclosures.investment is None
    assert view_model.disclosures.tax is None


def test_options_are_recommended_first_regardless_of_input_order() -> None:
    config = ConfigSnapshot()
    purchase_price = Decimal("285000.00")
    down_payment_pct = Decimal("0.05")

    def _scenario(rate: Decimal) -> ScenarioInputs:
        return ScenarioInputs(
            purchase_price=purchase_price,
            down_payment_pct=down_payment_pct,
            note_rate=rate,
            strategy=StrategyType.PRIMARY,
            fico=700,
            property_tax_annual_rate=Decimal("0.0085"),
            insurance_annual_rate=Decimal("0.005"),
        )

    par = _scenario(Decimal("0.065"))
    buydown = _scenario(Decimal("0.06125"))

    inputs = ReportInputs(
        first_name="Daniel",
        property_label="902 E Washington St, Indianapolis, IN 46201",
        purchase_price=purchase_price,
        strategy=StrategyType.PRIMARY,
        prepared_at=date(2026, 9, 25),
        rates_as_of=date(2026, 9, 25),
        expires_at=date(2026, 10, 16),
        expired=False,
        superseded=False,
        options=[
            # Buydown listed first in the input order -- builder must still
            # put the recommended option (Par) first in the output.
            ReportOptionInput(
                quote_id="buydown-quote",
                label="Buydown",
                recommended=False,
                note_rate=buydown.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=buydown.discount_points_pct,
                prepay_label="No prepayment penalty",
                computation=compute_quote(buydown, config),
            ),
            ReportOptionInput(
                quote_id="par-quote",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="No prepayment penalty",
                computation=compute_quote(par, config),
            ),
        ],
        recommendation_text="We recommend the par option.",
        lo_note=None,
        lo_name="Jordan Blake",
        lo_title="Loan Officer",
        lo_nmls="NMLS #1933377",
        lo_phone="(813) 555-0100",
        lo_email="jordan.blake@clearquote-demo.test",
    )

    view_model = build_report_view_model(inputs)

    assert [o.label for o in view_model.options] == ["Par", "Buydown"]
    # LTV 95% > 80% -- MI applies (primary with MI persona).
    assert any(
        line.label == "Mortgage insurance" for line in view_model.options[0].breakdown.payment_lines
    )


def test_switching_option_values_come_straight_from_the_fixture() -> None:
    """AC4: values differ per option and match the underlying computation
    exactly -- no recomputation happens anywhere downstream (this asserts the
    contract the frontend's OptionSwitcher relies on: it only ever indexes
    into `view_model.options`, never recomputes)."""
    view_model = build_report_view_model(_marcus_hale_inputs())
    par, buydown = view_model.options

    assert par.hero.monthly_payment != buydown.hero.monthly_payment
    assert par.rate != buydown.rate
    assert Decimal(par.breakdown.payment_lines[0].amount) == Decimal("1913.05")
