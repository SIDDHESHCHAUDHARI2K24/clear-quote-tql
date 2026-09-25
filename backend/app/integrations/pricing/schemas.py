"""`PricingRequestDTO`/`PricedProductDTO`: the mock Optimal Blue payload shapes.

Field names mirror `docs/design/data-field-catalog.md` section 6's outbound
search request JSON and inbound pricing return fields verbatim (PascalCase
request fields are OB's own wire names, not a style deviation).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PricingRequestDTO(BaseModel):
    """Every field is optional here so `MockPricingClient` can validate
    presence itself and name every missing required field at once
    (`PricingValidationError`), rather than failing on the first one
    pydantic's own required-field validation would reject.
    """

    model_config = ConfigDict(frozen=True)

    LoanPosition: str | None = None
    LoanType: str | None = None
    LoanPurpose: str | None = None
    BaseLoanAmount: Decimal | None = None
    TotalLoanAmount: Decimal | None = None
    PurchasePrice: Decimal | None = None
    AppraisedValue: Decimal | None = None
    LTV: Decimal | None = None
    CLTV: Decimal | None = None
    HCLTV: Decimal | None = None
    RepresentativeFICO: int | None = None
    Occupancy: str | None = None
    PropertyType: str | None = None
    NumberOfUnits: int | None = None
    State: str | None = None
    County: str | None = None
    ZipCode: str | None = None
    AmortizationType: str | None = None
    AmortizationTerm: int | None = None
    PrepaymentPenalty: str | None = None
    IncomeVerificationType: str | None = None
    DesiredLockDays: int | None = None

    # Conditionally required when Occupancy == "InvestmentProperty".
    DSCR: Decimal | None = None
    ShortTermRental: str | None = None

    # Optional on every request.
    Rural: str | None = None
    LeadSource: str | None = None
    AutomatedUW: str | None = None
    SelfEmployed: str | None = None
    FirstTimeHomeBuyer: str | None = None
    FirstTimeInvestor: str | None = None
    CorporateRelocation: str | None = None


class PricedProductDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    investor_name: str
    product_name: str
    lock_period_days: int
    note_rate: Decimal
    price_pct: Decimal
    discount_points_pct: Decimal
    discount_points_amount: Decimal
    is_par_rate: bool
    is_buydown_rate: bool
    piti_ob_estimate: Decimal | None = None
    """Always `None` -- the engine (CQ-008) recomputes P&I itself."""
