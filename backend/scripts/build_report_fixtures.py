"""Build `ReportViewModel` JSON fixtures for `packages/ui/src/report/__fixtures__/`.

Run via `uv run python backend/scripts/build_report_fixtures.py`. CQ-021
spec.md: "seed-independent fixtures ... a script builds `ReportViewModel`
JSON for Marcus Hale (STR), Kathleen McReynolds (LTR, TBD), Priya Nair
(primary) and Daniel Ortiz (primary with MI) by running `quote_engine` on
their persona inputs." Every number below traces to `compute_quote`, never
hand-typed -- this mirrors `seed/tests/test_personas_match_engine.py`'s own
"raw persona/provider fixtures -> engine -> assert" pattern, using the same
persona YAMLs and provider tables (`seed/personas/*.yaml`,
`seed/providers/*.yaml`) CQ-010 already seeds.

Also writes an expired variant (Marcus Hale, `header.expired = true`) and a
superseded variant (Priya Nair, `header.superseded = true`) per spec.md's
"Gallery page ... renders every component with each fixture, plus expired
and superseded variants."
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.quotes.report.builder import build_report_view_model
from app.features.quotes.report.inputs import ReportInputs, ReportMatchInput, ReportOptionInput
from app.features.quotes.report.schemas import ReportViewModel

OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "packages" / "ui" / "src" / "report" / "__fixtures__"
)

# mypy can't decompose a `**dict` splat against a dataclass's distinct
# keyword-only fields (it checks the whole dict against one positional slot
# instead), so these are passed as five explicit kwargs at each call site
# rather than `**_LO`.
_LO_NAME = "Jordan Blake"
_LO_TITLE = "Loan Officer"
_LO_NMLS = "NMLS #1933377"
_LO_PHONE = "(813) 555-0100"
_LO_EMAIL = "jordan.blake@clearquote-demo.test"
_PREPARED_AT = date(2026, 9, 25)
_RATES_AS_OF = date(2026, 9, 25)
_EXPIRES_AT = date(2026, 10, 16)


def _marcus_hale_inputs(*, expired: bool = False) -> ReportInputs:
    """STR, Tampa FL. Reproduces the pinned golden values (P&I $1,913.05 at
    7.500% par, year-1 tax savings $24,275.78) -- $342,000 purchase price,
    20% down, 7.500% note rate and default `ConfigSnapshot` are exactly
    `test_golden.py`'s shared STR scenario. Tax/insurance/STR-revenue come
    from the real seed provider tables (Hillsborough county, zip 33602)."""
    config = ConfigSnapshot()
    purchase_price = Decimal("342000.00")
    down_payment_pct = Decimal("0.20")
    str_gross_annual_revenue = Decimal("24000")  # seed/providers/str_revenue.yaml, zip 33602

    par = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.075"),
        strategy=StrategyType.STR,
        fico=760,
        property_tax_annual_rate=Decimal("0.0089"),  # seed/providers/tax_rates.yaml, Hillsborough
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
        prepared_at=_PREPARED_AT,
        rates_as_of=_RATES_AS_OF,
        expires_at=_EXPIRES_AT,
        expired=expired,
        superseded=False,
        options=[
            ReportOptionInput(
                quote_id="marcus-par",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="5-year prepayment penalty",
                computation=compute_quote(par, config),
            ),
            ReportOptionInput(
                quote_id="marcus-buydown",
                label="Buydown",
                recommended=False,
                note_rate=buydown.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=buydown.discount_points_pct,
                prepay_label="5-year prepayment penalty",
                computation=compute_quote(buydown, config),
            ),
        ],
        recommendation_text=(
            "We recommend the par option: it keeps cash to close lowest while "
            "the STR income offsets most of the payment."
        ),
        lo_note="Happy to walk through the numbers whenever works for you.",
        lo_name=_LO_NAME,
        lo_title=_LO_TITLE,
        lo_nmls=_LO_NMLS,
        lo_phone=_LO_PHONE,
        lo_email=_LO_EMAIL,
    )


def _kathleen_mcreynolds_matches(config: ConfigSnapshot) -> list[ReportMatchInput]:
    """CQ-023: 3 Davenport, FL listings (seed/providers/listings.yaml,
    all zip 33896 -- same county/rent-comp data as Kathleen's own subject
    market), run through her recommended (Par) option's terms: 25% down,
    7.250% note rate, 0% points, FICO 720. Same `compute_quote` call this
    whole script already makes for her own options -- no hand-typed money."""
    down_payment_pct = Decimal("0.25")
    tax_rate = Decimal("0.0089")  # Polk county
    insurance_rate = Decimal("0.005")  # FL default (Steadily)
    market_rent = Decimal("2250")  # seed/providers/rents.yaml, zip 33896

    listings = [
        (
            "102 Sample St, Davenport, FL 33896",
            "4 bd · 2 ba · 1,650 sqft",
            "good_buy",
            "Turnkey Davenport investment opportunity",
            "https://picsum.photos/seed/kathleen_mcreynolds/640/480",
            Decimal("255000.00"),
        ),
        (
            "112 Grove Ave, Davenport, FL 33896",
            "4 bd · 2 ba · 1,700 sqft",
            "good_buy",
            "Spacious Davenport rental near the theme-park corridor",
            "https://picsum.photos/seed/cq023_davenport_2/640/480",
            Decimal("280000.00"),
        ),
        (
            "111 Grove Ave, Davenport, FL 33896",
            "3 bd · 2 ba · 1,550 sqft",
            "great_buy",
            "Move-in ready Davenport rental",
            "https://picsum.photos/seed/cq023_davenport_1/640/480",
            Decimal("220000.00"),
        ),
    ]

    matches = []
    for address, bed_bath_sqft, deal_grade, tagline, image_url, price in listings:
        inputs = ScenarioInputs(
            purchase_price=price,
            down_payment_pct=down_payment_pct,
            note_rate=Decimal("0.0725"),
            strategy=StrategyType.LTR,
            fico=720,
            property_tax_annual_rate=tax_rate,
            insurance_annual_rate=insurance_rate,
            market_rent_ltr=market_rent,
        )
        computation = compute_quote(inputs, config)
        assert computation.qualifying_rent is not None
        assert computation.monthly_cashflow is not None
        assert computation.cap_rate_pct is not None
        assert computation.year_one_tax_savings is not None
        matches.append(
            ReportMatchInput(
                matched_property_id=address,
                property_image_url=image_url,
                property_address=address,
                bed_bath_sqft=bed_bath_sqft,
                deal_grade_badge=deal_grade,
                property_tagline=tagline,
                price=price,
                total_monthly_payment=computation.total_monthly_payment,
                rent_estimate=computation.qualifying_rent,
                rent_label="Market rent (LTR)",
                monthly_cashflow=computation.monthly_cashflow,
                cash_to_close=computation.cash_to_close,
                cap_rate_pct=computation.cap_rate_pct,
                year1_tax_savings=computation.year_one_tax_savings,
            )
        )

    # Spec.md: sorted by monthly cashflow descending.
    matches.sort(key=lambda m: m.monthly_cashflow or Decimal("-Infinity"), reverse=True)
    return matches


def _kathleen_mcreynolds_inputs() -> ReportInputs:
    """LTR, Davenport FL, subject property TBD (`property_address_status:
    TBD` in the persona YAML) -- renders "Property to be determined"."""
    config = ConfigSnapshot()
    purchase_price = Decimal("300000.00")
    down_payment_pct = Decimal("0.25")
    market_rent = Decimal("2250")  # seed/providers/rents.yaml, zip 33896

    par = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.0725"),
        strategy=StrategyType.LTR,
        fico=720,
        property_tax_annual_rate=Decimal("0.0089"),  # Polk county
        insurance_annual_rate=Decimal("0.005"),
        market_rent_ltr=market_rent,
    )
    buydown = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.06875"),
        strategy=StrategyType.LTR,
        fico=720,
        property_tax_annual_rate=Decimal("0.0089"),
        insurance_annual_rate=Decimal("0.005"),
        discount_points_pct=Decimal("0.01"),
        market_rent_ltr=market_rent,
    )

    return ReportInputs(
        first_name="Kathleen",
        property_label=None,
        purchase_price=purchase_price,
        strategy=StrategyType.LTR,
        prepared_at=_PREPARED_AT,
        rates_as_of=_RATES_AS_OF,
        expires_at=_EXPIRES_AT,
        expired=False,
        superseded=False,
        options=[
            ReportOptionInput(
                quote_id="kathleen-par",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="5-year prepayment penalty",
                computation=compute_quote(par, config),
            ),
            ReportOptionInput(
                quote_id="kathleen-buydown",
                label="Buydown",
                recommended=False,
                note_rate=buydown.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=buydown.discount_points_pct,
                prepay_label="5-year prepayment penalty",
                computation=compute_quote(buydown, config),
            ),
        ],
        recommendation_text="We recommend the par option for the strongest long-term cashflow.",
        lo_note=None,
        lo_name=_LO_NAME,
        lo_title=_LO_TITLE,
        lo_nmls=_LO_NMLS,
        lo_phone=_LO_PHONE,
        lo_email=_LO_EMAIL,
        matches=_kathleen_mcreynolds_matches(config),
    )


def _priya_nair_inputs(*, superseded: bool = False) -> ReportInputs:
    """Primary, Carmel IN -- 20% down (LTV 80%, no MI)."""
    config = ConfigSnapshot()
    purchase_price = Decimal("420000.00")
    down_payment_pct = Decimal("0.20")

    par = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.065"),
        strategy=StrategyType.PRIMARY,
        fico=760,
        property_tax_annual_rate=Decimal("0.0085"),  # Hamilton county
        insurance_annual_rate=Decimal("0.005"),
    )
    buydown = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.06125"),
        strategy=StrategyType.PRIMARY,
        fico=760,
        property_tax_annual_rate=Decimal("0.0085"),
        insurance_annual_rate=Decimal("0.005"),
        discount_points_pct=Decimal("0.01"),
    )

    return ReportInputs(
        first_name="Priya",
        property_label="18 Maple Ct, Carmel, IN 46032",
        purchase_price=purchase_price,
        strategy=StrategyType.PRIMARY,
        prepared_at=_PREPARED_AT,
        rates_as_of=_RATES_AS_OF,
        expires_at=_EXPIRES_AT,
        expired=False,
        superseded=superseded,
        options=[
            ReportOptionInput(
                quote_id="priya-par",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="No prepayment penalty",
                computation=compute_quote(par, config),
            ),
            ReportOptionInput(
                quote_id="priya-buydown",
                label="Buydown",
                recommended=False,
                note_rate=buydown.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=buydown.discount_points_pct,
                prepay_label="No prepayment penalty",
                computation=compute_quote(buydown, config),
            ),
        ],
        recommendation_text="We recommend the par option for the lowest total cost.",
        lo_note=None,
        lo_name=_LO_NAME,
        lo_title=_LO_TITLE,
        lo_nmls=_LO_NMLS,
        lo_phone=_LO_PHONE,
        lo_email=_LO_EMAIL,
    )


def _daniel_ortiz_inputs() -> ReportInputs:
    """Primary, Indianapolis IN, 5% down (LTV 95% -- MI applies)."""
    config = ConfigSnapshot()
    purchase_price = Decimal("285000.00")
    down_payment_pct = Decimal("0.05")

    par = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.065"),
        strategy=StrategyType.PRIMARY,
        fico=700,
        property_tax_annual_rate=Decimal("0.0085"),  # Marion county
        insurance_annual_rate=Decimal("0.005"),
    )

    return ReportInputs(
        first_name="Daniel",
        property_label="902 E Washington St, Indianapolis, IN 46201",
        purchase_price=purchase_price,
        strategy=StrategyType.PRIMARY,
        prepared_at=_PREPARED_AT,
        rates_as_of=_RATES_AS_OF,
        expires_at=_EXPIRES_AT,
        expired=False,
        superseded=False,
        options=[
            ReportOptionInput(
                quote_id="daniel-par",
                label="Par",
                recommended=True,
                note_rate=par.note_rate,
                down_payment_pct=down_payment_pct,
                discount_points_pct=par.discount_points_pct,
                prepay_label="No prepayment penalty",
                computation=compute_quote(par, config),
            ),
        ],
        recommendation_text="We recommend the par option to get you to closing fastest.",
        lo_note="Let me know if you'd rather look at a lower down payment.",
        lo_name=_LO_NAME,
        lo_title=_LO_TITLE,
        lo_nmls=_LO_NMLS,
        lo_phone=_LO_PHONE,
        lo_email=_LO_EMAIL,
    )


def _write(name: str, view_model: ReportViewModel) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(json.dumps(view_model.model_dump(mode="json"), indent=2) + "\n")
    return path


def build_all() -> list[Path]:
    written: list[Path] = []
    written.append(_write("marcus_hale", build_report_view_model(_marcus_hale_inputs())))
    written.append(
        _write(
            "marcus_hale_expired",
            build_report_view_model(_marcus_hale_inputs(expired=True)),
        )
    )
    written.append(
        _write("kathleen_mcreynolds", build_report_view_model(_kathleen_mcreynolds_inputs()))
    )
    written.append(_write("priya_nair", build_report_view_model(_priya_nair_inputs())))
    written.append(
        _write(
            "priya_nair_superseded",
            build_report_view_model(_priya_nair_inputs(superseded=True)),
        )
    )
    written.append(_write("daniel_ortiz", build_report_view_model(_daniel_ortiz_inputs())))
    return written


if __name__ == "__main__":
    for path in build_all():
        print(f"Wrote {path}")
