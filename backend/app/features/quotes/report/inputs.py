"""`ReportInputs` -- the pure, DB-free input contract to `build_report_view_model`.

CQ-021 spec.md: "It does not read the database, so this item does not wait
for CQ-007; CQ-019 and CQ-022 map their models into `ReportInputs`." These
are plain frozen dataclasses (not Pydantic) precisely so nothing here can
accidentally acquire I/O or validation side effects beyond what the caller
already did -- `QuoteComputation` (already validated, already `Decimal`,
already engine-computed) is the only numeric payload; everything else here
is presentation metadata the builder formats but never recomputes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.features.pricing.engine.types import QuoteComputation, StrategyType


@dataclass(frozen=True)
class ReportOptionInput:
    """One priced option (a `Quote` row, mapped by the caller) plus the
    scenario-level inputs needed to label it -- `note_rate`/`down_payment_pct`
    aren't on `QuoteComputation` (only their *outputs* -- `loan_amount`,
    `ltv_pct` -- are), so the caller passes them alongside the computation.
    """

    quote_id: str
    label: str
    """Par / Buydown / Manual -- whatever `quotes.label` already holds."""
    recommended: bool
    note_rate: Decimal
    """Fraction, e.g. `Decimal("0.075")` for 7.500%."""
    down_payment_pct: Decimal
    """Fraction, e.g. `Decimal("0.20")` for 20%."""
    discount_points_pct: Decimal
    """Fraction, e.g. `Decimal("0.00875")` for 0.875 points. Matches
    `ScenarioInputs.discount_points_pct`'s sign convention (negative = credit)."""
    prepay_label: str
    """E.g. "5-year prepay", "No prepayment penalty". Investment only in
    practice (system-design.md), but the builder does not enforce that --
    the caller decides what to pass."""
    computation: QuoteComputation
    """The engine's full output for this option. `compute_quote`'s return
    value, unmodified -- the builder reads fields off it and formats them
    as strings; it never recomputes anything the engine already computed."""
    str_gross_annual_revenue: Decimal | None = None
    """STR only: `ScenarioInputs.str_gross_annual_revenue`, the raw
    pre-expense-ratio AirDNA figure. `QuoteComputation.underwritten_str_rent`
    is already net of the expense ratio, so the cashflow table's "gross
    revenue" row (spec.md) needs this raw input too -- it is not itself
    money math, the same annual->monthly /12 conversion `underwritten_str_rent`
    already does inside the engine."""


@dataclass(frozen=True)
class ReportMatchInput:
    """Placeholder shape for CQ-023's property-match cards (data-field-catalog
    §11). CQ-021 always passes an empty `matches` list (spec.md: "matches[]:
    empty here; filled by CQ-023") -- this type exists so `ReportInputs`'
    field has a concrete element type today instead of `list[Any]`, which
    CQ-023 can widen/adjust without touching `ReportViewModel`'s top-level
    shape."""

    matched_property_id: str
    property_image_url: str
    property_address: str
    bed_bath_sqft: str
    deal_grade_badge: str
    property_tagline: str
    price: Decimal


@dataclass(frozen=True)
class ReportInputs:
    """Everything `build_report_view_model` needs, already resolved by the
    caller (CQ-019's draft builder or CQ-022's sent-version reader) from
    whatever DB rows/session data it holds. No field here is read from a
    database by this module."""

    first_name: str
    property_label: str | None
    """`None` renders as "Property to be determined" (spec.md header)."""
    purchase_price: Decimal
    strategy: StrategyType
    prepared_at: date
    rates_as_of: date
    expires_at: date | None
    expired: bool
    superseded: bool
    options: list[ReportOptionInput]
    """Any order; the builder sorts recommended-first (spec.md: "options[]
    (recommended first)")."""
    recommendation_text: str
    lo_note: str | None
    lo_name: str
    lo_title: str
    lo_nmls: str
    lo_phone: str
    lo_email: str
    matches: list[ReportMatchInput] = field(default_factory=list)
