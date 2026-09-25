"""`LoanFileDTO`: the mock Encompass LOS's full 1003 payload.

Field names and types follow `docs/design/data-field-catalog.md` sections
1 (borrower/co-borrower profile), 2 (housing history), 4 (property/buy-box
geography) and 5 (loan structure & guideline setup) -- the sections
system-design.md's "Emulated integrations" table points `LosClient` at.

Every field besides `loan_number` is optional: `provider_los_records.payload`
is a free-form JSONB blob (CQ-007), and CQ-010's seed personas aren't landed
yet, so this item's own tests build partial fixture payloads directly
(including persona 7's exact failure mode -- an empty `occupancy_type`).

CQ-010 addition (plan.md decision #4): `employment`, `liabilities` and
`assets` cover catalog §3 ("Credit, assets & liabilities fields" -- sourced
from Encompass's "Import Liabilities" action and bank-statement verification)
and override O12 (employment fields added for primary loans). Nothing else
reads `LoanFileDTO` yet, so these are a pure, additive extension of CQ-009's
DTO rather than a behavior change -- `applications.service.import_from_los`
(CQ-010) is the only reader, and it owns writing `employment`, `liabilities`
and `assets` rows per the item's spec.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class LosEmploymentDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    employer_name: str | None = None
    monthly_income: Decimal | None = None
    years_at_job: Decimal | None = None
    self_employed: bool = False


class LosLiabilityDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    creditor_name: str
    account_type: str
    monthly_payment: Decimal
    balance: Decimal


class LosAssetDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_type: str | None = None
    institution: str | None = None
    verified_amount: Decimal


class LoanFileDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    loan_number: str

    # Section 1 -- borrower & co-borrower profile
    borrower_first_name: str | None = None
    borrower_last_name: str | None = None
    borrower_full_name: str | None = None
    borrower_ssn: str | None = None
    borrower_dob: date | None = None
    marital_status: str | None = None
    dependents_count: int | None = None
    borrower_email: str | None = None
    borrower_cell_phone: str | None = None
    borrower_home_phone: str | None = None
    borrower_work_phone: str | None = None
    has_co_borrower: bool | None = None
    no_co_applicant_check: bool | None = None
    co_borrower_full_name: str | None = None
    co_borrower_ssn: str | None = None
    co_borrower_dob: date | None = None
    """Not in the catalog's own §1 table, but `application_parties.dob` /
    CQ-012's `dob_format` rule apply to both roles (see that rule's own
    `_DOB_FIELD_KEY` map) -- added so a co-borrower can actually be imported
    with one (CQ-010 addition, plan.md decision #4)."""
    business_vesting: str | None = None
    llc_entity_name: str | None = None

    # Section 2 -- housing history & verification
    current_street_address: str | None = None
    current_city: str | None = None
    current_state: str | None = None
    current_zip: str | None = None
    current_housing_status: str | None = None
    current_residence_years: int | None = None
    current_residence_months: int | None = None
    previous_street_address: str | None = None
    previous_residence_years: int | None = None
    vom_completed: bool | None = None

    # Section 4 -- property & buy-box geography
    has_subject_property: bool | None = None
    property_address_status: str | None = None
    subject_street_address: str | None = None
    subject_city: str | None = None
    subject_state: str | None = None
    subject_zip: str | None = None
    subject_county: str | None = None
    property_type: str | None = None
    number_of_units: int | None = None
    number_of_stories: int | None = None
    buy_box_states: list[str] | None = None
    buy_box_market_cities: list[str] | None = None

    # Section 5 -- loan structure & guideline setup
    loan_purpose: str | None = None
    occupancy_type: str | None = None
    investment_strategy: str | None = None
    loan_program_name: str | None = None
    amortization_term_years: int | None = None
    amortization_type: str | None = None
    purchase_price: Decimal | None = None
    appraised_value: Decimal | None = None
    down_payment_pct: Decimal | None = None
    down_payment_amount: Decimal | None = None
    base_loan_amount: Decimal | None = None
    total_loan_amount: Decimal | None = None
    ltv: Decimal | None = None
    cltv: Decimal | None = None
    hcltv: Decimal | None = None
    prepayment_penalty_term: str | None = None
    automated_uw_system: str | None = None
    lead_source: str | None = None

    # CQ-010 addition -- catalog §3 / override O12 (see module docstring).
    employment: list[LosEmploymentDTO] = []
    liabilities: list[LosLiabilityDTO] = []
    assets: list[LosAssetDTO] = []
