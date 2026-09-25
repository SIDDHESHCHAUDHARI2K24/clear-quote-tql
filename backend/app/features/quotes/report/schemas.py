"""`ReportViewModel` -- the one data contract CQ-019 (LO preview) and CQ-022
(borrower report) both render, per spec.md's binding shape.

Every money/rate/percent field is a **decimal string** (`Decimal` formatted
server-side, e.g. `"1913.05"`, `"7.500"`, `"20.00"`), never a JSON number and
never a bare `Decimal` (which Pydantic would otherwise emit as a float-ish
JSON number and which loses the "frontend never does math on this" property
by inviting `Number(x) + Number(y)`-style arithmetic in components). Fields
that are strings can still be `Number()`-coerced for `Intl.NumberFormat`
display, which is not arithmetic (spec.md AC5) -- packages/ui/src/report's
`report-no-money-math.test.ts` enforces that no `+ - * /` operator is ever
applied to a component's money/rate/percent props.

`build_report_view_model` (builder.py) is the only place these strings are
produced; nothing in packages/ui recomputes them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReportStrategy(StrEnum):
    """Lowercase mirror of `pricing.engine.types.StrategyType`, per spec.md's
    binding `strategy`: `primary` | `ltr` | `str` (the engine's own enum is
    uppercase `PRIMARY`/`LTR`/`STR` -- this is a presentation-layer rename,
    not a new business concept)."""

    PRIMARY = "primary"
    LTR = "ltr"
    STR = "str"


class ReportHeader(BaseModel):
    model_config = ConfigDict(frozen=True)

    first_name: str
    property_label: str
    """Address, or "Property to be determined" when TBD."""
    purchase_price: str
    prepared_at: str
    """ISO date, e.g. `"2026-09-25"`."""
    rates_as_of: str
    expires_at: str | None
    expired: bool
    superseded: bool


class BreakdownLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    amount: str
    """May be negative (e.g. a seller-credit line), still a decimal string."""


class Breakdown(BaseModel):
    model_config = ConfigDict(frozen=True)

    payment_lines: list[BreakdownLine]
    payment_total: str
    cash_to_close_lines: list[BreakdownLine]
    cash_to_close_total: str


class HeroNumbers(BaseModel):
    model_config = ConfigDict(frozen=True)

    monthly_payment: str
    cash_to_close: str
    loan_amount: str | None
    """Primary only (with `rate`, forms "$273,600 at 7.500%")."""
    monthly_cashflow: str | None
    """Investment only. May be negative."""
    year1_tax_savings: str | None
    """Investment only."""
    year1_tax_savings_monthly: str | None
    """Investment only. Whole-dollar approximation for "≈ $2,023/mo"
    (already rounded server-side -- the frontend prepends "≈ $" and appends
    "/mo", it does not divide by 12 itself)."""


class CashflowTable(BaseModel):
    model_config = ConfigDict(frozen=True)

    rent_label: str
    """"Market rent (LTR)" or "Gross STR revenue"."""
    gross_amount: str
    expense_ratio: str | None
    """STR only (e.g. `"20.00"` for 20%); `None` for LTR."""
    qualifying_rent: str
    pitia: str
    monthly_cashflow: str
    annual_cashflow: str
    dscr: str
    cap_rate_pct: str
    monthly_cashflow_incl_tax: str


class CostSegTable(BaseModel):
    model_config = ConfigDict(frozen=True)

    purchase_price: str
    land_allocation_pct: str
    land_value_allocation: str
    depreciable_building_basis: str
    accelerated_property_pct: str
    accelerated_basis_amount: str
    bonus_depreciation_pct: str
    year_one_tax_deduction: str
    investor_marginal_tax_rate: str
    year_one_tax_savings: str


class ReportOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    quote_id: str
    label: str
    recommended: bool
    rate: str
    """Percent, e.g. `"7.500"`."""
    points_pct: str
    """Percent, e.g. `"0.875"` or `"0.000"` at par."""
    points_amount: str
    down_payment_pct: str
    """Percent, e.g. `"20.00"`."""
    prepay_label: str
    hero: HeroNumbers
    breakdown: Breakdown
    cashflow: CashflowTable | None
    """Investment only; `None` for primary."""
    cost_seg: CostSegTable | None
    """Investment only; `None` for primary."""


class ReportRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    lo_note: str | None


class ReportMatch(BaseModel):
    """Placeholder shape for CQ-023's match cards (data-field-catalog §11).
    Always `[]` in CQ-021's own fixtures/tests."""

    model_config = ConfigDict(frozen=True)

    matched_property_id: str
    property_image_url: str
    property_address: str
    bed_bath_sqft: str
    deal_grade_badge: str
    property_tagline: str
    price: str


class ReportDisclosures(BaseModel):
    model_config = ConfigDict(frozen=True)

    core: str
    investment: str | None
    tax: str | None


class ReportLo(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    title: str
    nmls: str
    phone: str
    email: str


class ReportViewModel(BaseModel):
    """The one contract. See module docstring."""

    model_config = ConfigDict(frozen=True)

    header: ReportHeader
    strategy: ReportStrategy
    options: list[ReportOption]
    recommendation: ReportRecommendation
    matches: list[ReportMatch]
    disclosures: ReportDisclosures
    lo: ReportLo


def report_view_model_openapi_components() -> dict[str, dict[str, Any]]:
    """`components/schemas` entries for `ReportViewModel` and every model it
    references, keyed by name, ready to merge into an `app.openapi()` dict.

    CQ-021 has no DB-backed endpoint of its own (the builder is pure and
    reads no DB; see inputs.py) -- CQ-019/CQ-022 will expose `ReportViewModel`
    through real endpoints later. Rather than add a throwaway endpoint just
    to get the type into the OpenAPI schema (spec.md explicitly calls that
    "not ideal"), `app.main.create_app()` merges this dict into
    `components/schemas` directly, so `make api-client` generates the
    TypeScript type today and CQ-019/CQ-022 can build against it. See
    CQ-021 plan.md Decision 1.
    """
    full_schema = ReportViewModel.model_json_schema(ref_template="#/components/schemas/{model}")
    defs = full_schema.pop("$defs", {})
    components: dict[str, dict[str, Any]] = dict(defs)
    components["ReportViewModel"] = full_schema
    return components
