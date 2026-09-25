"""Response/request shapes for the verification-tab API (CQ-028a)."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import (
    ApplicationStatus,
    ApplicationTab,
    FieldSource,
    FlagSeverity,
    Occupancy,
)
from app.features.applications.housing.models import HousingStatus
from app.features.applications.property.models import PropertyType
from app.features.borrower.consent.models import ConsentStatus

JsonValue = str | int | bool | list[str] | None


class SectionTab(enum.StrEnum):
    BORROWERS = "borrowers"
    HOUSING = "housing"
    CREDIT = "credit"
    ASSETS = "assets"
    PROPERTY = "property"


class SectionField(BaseModel):
    field_key: str
    label: str
    value: JsonValue
    source: FieldSource
    overridden: bool
    original_value: JsonValue = None
    editable: bool = True


RecordKind = Literal[
    "party",
    "housing_history",
    "liability",
    "asset",
    "employment",
    "document",
    "property",
    "loan",
    "credit",
]


class SectionRecord(BaseModel):
    kind: RecordKind
    id: uuid.UUID | None
    role: str | None = None
    """`borrower` / `co_borrower` for party records."""
    manual: bool = False
    """Added by the LO (not imported)."""
    fields: list[SectionField]


class SectionFlag(BaseModel):
    id: uuid.UUID
    tab: ApplicationTab
    field_key: str
    rule: str
    severity: FlagSeverity
    message: str | None


class HousingSummary(BaseModel):
    total_months: int
    required_months: int
    meets_requirement: bool


class ConsentSummary(BaseModel):
    """E11: latest hard-pull consent request (CQ-033 fills the decision)."""

    id: uuid.UUID
    status: ConsentStatus
    requested_at: datetime | None
    requested_by: uuid.UUID | None
    expires_at: datetime | None
    decided_at: datetime | None
    decline_reason: str | None
    fico_after_pull: int | None


DtiStatus = Literal["ok", "awaiting_pricing", "no_income", "not_applicable"]


class CreditSummary(BaseModel):
    representative_fico: int | None
    fico_bracket: str | None
    pull_type: Literal["soft_pull", "hard_pull"] | None
    pulled_at: datetime | None
    liabilities_monthly_total: Decimal
    dti_applicable: bool
    """`False` for investment loans: the UI shows no DTI (AC8)."""
    dti: Decimal | None
    """0-1 fraction, 4 dp; `None` unless `dti_status == "ok"`."""
    dti_status: DtiStatus
    consent: ConsentSummary | None


class DocumentItem(BaseModel):
    id: uuid.UUID
    doc_type: str
    received: bool
    received_at: datetime | None


AssetsStatus = Literal["sufficient", "insufficient", "awaiting_pricing"]


class AssetsSummary(BaseModel):
    verified_assets_total: Decimal
    reserves_months: int
    reserves_required: Decimal | None
    cash_to_close: Decimal | None
    required_funds: Decimal | None
    status: AssetsStatus
    income_applicable: bool
    """`True` only for primary loans (employment + income shown, AC8)."""
    monthly_income_total: Decimal | None
    documents: list[DocumentItem]


class PropertySummary(BaseModel):
    tbd: bool
    recommend_matches: bool
    buy_box_states: list[str]
    buy_box_metros: list[str]


class ResumeResult(BaseModel):
    requested: bool
    reason: str


class SectionResponse(BaseModel):
    application_id: uuid.UUID
    tab: SectionTab
    status: ApplicationStatus
    occupancy: Occupancy | None
    records: list[SectionRecord]
    flags: list[SectionFlag]
    housing: HousingSummary | None = None
    credit: CreditSummary | None = None
    assets: AssetsSummary | None = None
    property: PropertySummary | None = None
    resume: ResumeResult | None = None
    """Set on edit responses: whether the pipeline was resumed."""


# --- requests --------------------------------------------------------------


class FieldEditRequest(BaseModel):
    value: JsonValue


class HousingCreate(BaseModel):
    street_address: str = Field(min_length=1)
    city: str = Field(min_length=1)
    state: str = Field(pattern=r"^[A-Za-z]{2}$")
    zip: str = Field(pattern=r"^\d{5}$")
    housing_status: HousingStatus
    residence_years: int = Field(ge=0, le=80)
    residence_months: int = Field(ge=0, le=11)
    vom_completed: bool = False


class HousingPatch(BaseModel):
    street_address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    housing_status: HousingStatus | None = None
    residence_years: int | None = None
    residence_months: int | None = None
    vom_completed: bool | None = None


class PartyCreate(BaseModel):
    """Adds the co-borrower (the only party the LO can add)."""

    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    ssn: str | None = None
    dob: date | None = None
    email: str | None = None
    cell_phone: str | None = None
    home_phone: str | None = None
    work_phone: str | None = None


class PartyPatch(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    ssn: str | None = None
    dob: date | None = None
    marital_status: str | None = None
    dependents_count: int | None = None
    email: str | None = None
    cell_phone: str | None = None
    home_phone: str | None = None
    work_phone: str | None = None
    business_vesting: str | None = None
    llc_entity_name: str | None = None
    no_co_applicant_check: bool | None = None


class LiabilityCreate(BaseModel):
    creditor_name: str = Field(min_length=1)
    account_type: str = Field(min_length=1)
    monthly_payment: Decimal = Field(ge=0)
    balance: Decimal = Field(ge=0)


class LiabilityPatch(BaseModel):
    creditor_name: str | None = None
    account_type: str | None = None
    monthly_payment: Decimal | None = None
    balance: Decimal | None = None


class SsnRevealResponse(BaseModel):
    party_id: uuid.UUID
    ssn: str | None


class HardPullRequestResponse(BaseModel):
    consent: ConsentSummary
    section: SectionResponse


class AddressInput(BaseModel):
    street_address: str = Field(min_length=1)
    city: str = Field(min_length=1)
    state: str = Field(pattern=r"^[A-Za-z]{2}$")
    zip: str = Field(pattern=r"^\d{5}$")
    county: str | None = None


class PropertyPatch(BaseModel):
    """Every key optional; `address` and `tbd=true` are mutually exclusive."""

    address: AddressInput | None = None
    tbd: bool | None = None
    recommend_matches: bool | None = None
    buy_box_states: list[str] | None = None
    buy_box_metros: list[str] | None = None
    property_type: PropertyType | None = None
    number_of_units: int | None = Field(default=None, ge=1, le=4)


class DocumentPatch(BaseModel):
    received: bool
