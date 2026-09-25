"""Per-tab validation for the apply wizard (CQ-032 spec table; plan.md
decisions 5-10 and the "Per-tab data contract").

One set of pydantic models shared by autosave (`PATCH .../draft`, which
reports `field_errors` but never blocks the save) and submit (which
requires every tab to pass). Cross-tab rules read a `ValidationContext`
passed as pydantic's validation `context`:

- tab 3's "income required for primary" needs tab 2's occupancy;
- tab 4's typed-name rule needs tab 1's name;
- tab 2's metro rule needs the known metro list (state -> metros).

Errors come back as `{dotted.path: message}` with plain-English messages
(pydantic's defaults are rewritten in `_message`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.clock import now


class TabName(StrEnum):
    YOU = "you"
    PROPERTY = "property"
    INCOME = "income"
    CONSENT = "consent"


TAB_ORDER: tuple[TabName, ...] = (
    TabName.YOU,
    TabName.PROPERTY,
    TabName.INCOME,
    TabName.CONSENT,
)

MIN_AGE_YEARS = 18
MAX_AGE_YEARS = 120
MIN_HOUSING_MONTHS = 24

DOWN_PAYMENT_OPTIONS: dict[str, tuple[Decimal, ...]] = {
    "primary": (
        Decimal("0.03"),
        Decimal("0.05"),
        Decimal("0.10"),
        Decimal("0.15"),
        Decimal("0.20"),
    ),
    "ltr": (Decimal("0.15"), Decimal("0.20"), Decimal("0.25")),
    "str": (Decimal("0.15"), Decimal("0.20"), Decimal("0.25")),
}
"""Catalog section 5 (`down_payment_pct`): primary 3/5/10/15/20%,
investment 15/20/25%."""

MSG_REQUIRED = "This field is required."
MSG_PHONE = "Enter a 10-digit phone number."
MSG_AGE = "You must be at least 18 years old."
MSG_DOB_RANGE = "Enter a valid date of birth."
MSG_SSN = "SSN must be 9 digits."
MSG_STATE = "Use the 2-letter state code."
MSG_ZIP = "ZIP code must be 5 digits."
MSG_PRIOR_ADDRESS = "Add your prior address (you've lived at your current address under 2 years)."
MSG_PRICE = "Enter a price greater than 0."
MSG_METRO_REQUIRED = "Choose at least one metro."
MSG_METRO_UNKNOWN = "Choose a metro from the list."
MSG_DOWN_PAYMENT = "Choose one of the listed down payments."
MSG_NON_NEGATIVE = "Must be 0 or more."
MSG_INCOME_PRIMARY = "Monthly income is required for a home you'll live in."
MSG_CHECKBOX = "Check this box to continue."
MSG_TYPED_NAME = "Type your full name exactly as entered on step 1."
MSG_EMAIL = "Enter a valid email address."

_STATE_RE = re.compile(r"^[A-Za-z]{2}$")
_ZIP_RE = re.compile(r"^\d{5}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class ValidationContext:
    """Cross-tab inputs for the per-tab models."""

    occupancy: str | None = None
    """Tab 2's `occupancy` (`primary`/`ltr`/`str`), for tab 3."""
    full_name: str | None = None
    """Tab 1's `first_name last_name`, for tab 4."""
    known_metros: dict[str, frozenset[str]] = field(default_factory=dict)
    """State code -> metro names (from `provider_listings`), for tab 2."""
    today: date | None = None


def _ctx(info: ValidationInfo) -> ValidationContext:
    context = info.context
    if isinstance(context, ValidationContext):
        return context
    return ValidationContext()


def _custom(message: str) -> PydanticCustomError:
    return PydanticCustomError("apply_rule", message)


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class _TabModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class Address(_TabModel):
    street: str
    city: str
    state: str
    zip: str

    @field_validator("street", "city")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value:
            raise _custom(MSG_REQUIRED)
        return value

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        if not _STATE_RE.fullmatch(value):
            raise _custom(MSG_STATE)
        return value.upper()

    @field_validator("zip")
    @classmethod
    def _zip(cls, value: str) -> str:
        if not _ZIP_RE.fullmatch(value):
            raise _custom(MSG_ZIP)
        return value


class PriorAddress(Address):
    residence_years: int
    residence_months: int

    @field_validator("residence_years")
    @classmethod
    def _years(cls, value: int) -> int:
        if value < 0 or value > 99:
            raise _custom("Enter 0 to 99 years.")
        return value

    @field_validator("residence_months")
    @classmethod
    def _months(cls, value: int) -> int:
        if value < 0 or value > 11:
            raise _custom("Enter 0 to 11 months.")
        return value


class PersonFields(_TabModel):
    first_name: str
    last_name: str
    cell_phone: str
    dob: date
    ssn: str
    marital_status: Literal["married", "unmarried", "separated"]
    dependents_count: int

    @field_validator("first_name", "last_name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value:
            raise _custom(MSG_REQUIRED)
        if len(value) > 100:
            raise _custom("Use 100 characters or fewer.")
        return value

    @field_validator("cell_phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        digits = digits_only(value)
        if len(digits) != 10:
            raise _custom(MSG_PHONE)
        return digits

    @field_validator("ssn")
    @classmethod
    def _ssn(cls, value: str) -> str:
        if not re.fullmatch(r"[\d\s-]+", value) or len(digits_only(value)) != 9:
            raise _custom(MSG_SSN)
        return digits_only(value)

    @field_validator("dob")
    @classmethod
    def _dob(cls, value: date, info: ValidationInfo) -> date:
        today = _ctx(info).today or now().date()
        age = _age_on(value, today)
        if value >= today or age > MAX_AGE_YEARS:
            raise _custom(MSG_DOB_RANGE)
        if age < MIN_AGE_YEARS:
            raise _custom(MSG_AGE)
        return value

    @field_validator("dependents_count")
    @classmethod
    def _dependents(cls, value: int) -> int:
        if value < 0:
            raise _custom(MSG_NON_NEGATIVE)
        return value


class CoBorrower(PersonFields):
    email: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not _EMAIL_RE.fullmatch(value):
            raise _custom(MSG_EMAIL)
        return value


class YouTab(PersonFields):
    """Tab 1. `email` is not part of the tab: it is the account email,
    read-only (plan.md decision 3)."""

    current_address: Address
    housing_status: Literal["own", "rent", "rent_free"]
    residence_years: int
    residence_months: int
    prior_address: PriorAddress | None = None
    has_co_borrower: bool = False
    co_borrower: CoBorrower | None = None

    @field_validator("residence_years")
    @classmethod
    def _years(cls, value: int) -> int:
        if value < 0 or value > 99:
            raise _custom("Enter 0 to 99 years.")
        return value

    @field_validator("residence_months")
    @classmethod
    def _months(cls, value: int) -> int:
        if value < 0 or value > 11:
            raise _custom("Enter 0 to 11 months.")
        return value

    @model_validator(mode="after")
    def _conditionals(self) -> YouTab:
        months = self.residence_years * 12 + self.residence_months
        if months < MIN_HOUSING_MONTHS and self.prior_address is None:
            raise PydanticCustomError("prior_address", MSG_PRIOR_ADDRESS)
        if self.has_co_borrower and self.co_borrower is None:
            raise PydanticCustomError("co_borrower", MSG_REQUIRED)
        return self

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class PropertyTab(_TabModel):
    occupancy: Literal["primary", "ltr", "str"]
    has_property: bool
    address: Address | None = None
    buy_box_states: list[str] = []
    buy_box_metros: list[str] = []
    target_price: Decimal
    down_payment_pct: Decimal

    @field_validator("target_price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise _custom(MSG_PRICE)
        if value >= Decimal("10000000000"):
            raise _custom("Enter a realistic price.")
        return value

    @field_validator("buy_box_states")
    @classmethod
    def _states(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for state in value:
            if not _STATE_RE.fullmatch(state.strip()):
                raise _custom(MSG_STATE)
            upper = state.strip().upper()
            if upper not in cleaned:
                cleaned.append(upper)
        return cleaned

    @field_validator("buy_box_metros")
    @classmethod
    def _metros(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for metro in value:
            name = metro.strip()
            if name and name not in cleaned:
                cleaned.append(name)
        return cleaned

    @model_validator(mode="after")
    def _conditionals(self, info: ValidationInfo) -> PropertyTab:
        allowed = DOWN_PAYMENT_OPTIONS[self.occupancy]
        if self.down_payment_pct not in allowed:
            raise PydanticCustomError("down_payment_pct", MSG_DOWN_PAYMENT)
        if self.has_property:
            if self.address is None:
                raise PydanticCustomError("address", MSG_REQUIRED)
            return self
        if not self.buy_box_metros:
            raise PydanticCustomError("buy_box_metros", MSG_METRO_REQUIRED)
        known = _ctx(info).known_metros
        allowed_metros = {
            metro for state in self.buy_box_states for metro in known.get(state, frozenset())
        }
        if any(metro not in allowed_metros for metro in self.buy_box_metros):
            raise PydanticCustomError("buy_box_metros", MSG_METRO_UNKNOWN)
        return self


class IncomeTab(_TabModel):
    employer_name: str | None = None
    years_employed: Decimal | None = None
    monthly_income: Decimal | None = None
    monthly_debts: Decimal | None = None
    liquid_assets: Decimal

    @field_validator("years_employed", "monthly_income", "monthly_debts", "liquid_assets")
    @classmethod
    def _non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if not value.is_finite() or value < 0:
            raise _custom(MSG_NON_NEGATIVE)
        if value >= Decimal("10000000000"):
            raise _custom("Enter a realistic amount.")
        return value

    @field_validator("employer_name")
    @classmethod
    def _employer(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _primary_requires_income(self, info: ValidationInfo) -> IncomeTab:
        if _ctx(info).occupancy != "primary":
            return self
        if self.monthly_income is None or self.monthly_income <= 0:
            raise PydanticCustomError("monthly_income", MSG_INCOME_PRIMARY)
        for name in ("employer_name", "years_employed", "monthly_debts"):
            if getattr(self, name) is None:
                raise PydanticCustomError(name, MSG_REQUIRED)
        return self


class ConsentTab(_TabModel):
    soft_pull_authorized: bool
    contact_consent: bool
    terms_accepted: bool
    typed_name: str

    @field_validator("soft_pull_authorized", "contact_consent", "terms_accepted")
    @classmethod
    def _checked(cls, value: bool) -> bool:
        if value is not True:
            raise _custom(MSG_CHECKBOX)
        return value

    @field_validator("typed_name")
    @classmethod
    def _typed_name(cls, value: str, info: ValidationInfo) -> str:
        expected = _ctx(info).full_name
        if not value or expected is None or normalize_name(value) != normalize_name(expected):
            raise _custom(MSG_TYPED_NAME)
        return value


TAB_MODELS: dict[TabName, type[_TabModel]] = {
    TabName.YOU: YouTab,
    TabName.PROPERTY: PropertyTab,
    TabName.INCOME: IncomeTab,
    TabName.CONSENT: ConsentTab,
}

# Model-level (cross-field) errors raised as `PydanticCustomError(<field>,
# message)` carry the field path in the error *type*; everything else is
# located by pydantic's own `loc`.
_MODEL_LEVEL_FIELDS = {
    "prior_address",
    "co_borrower",
    "down_payment_pct",
    "address",
    "buy_box_metros",
    "monthly_income",
    "employer_name",
    "years_employed",
    "monthly_debts",
}

_PYDANTIC_MESSAGES: dict[str, str] = {
    "missing": MSG_REQUIRED,
    "bool_type": "Choose yes or no.",
    "bool_parsing": "Choose yes or no.",
    "int_type": "Enter a whole number.",
    "int_parsing": "Enter a whole number.",
    "int_from_float": "Enter a whole number.",
    "decimal_type": "Enter a number.",
    "decimal_parsing": "Enter a number.",
    "date_type": "Enter a date as YYYY-MM-DD.",
    "date_parsing": "Enter a date as YYYY-MM-DD.",
    "date_from_datetime_parsing": "Enter a date as YYYY-MM-DD.",
    "literal_error": "Choose one of the options.",
    "string_type": "Enter text.",
    "list_type": "Choose from the list.",
    "model_type": "This section is incomplete.",
    "dict_type": "This section is incomplete.",
}


def _message(error: Any) -> str:
    if error["type"] == "apply_rule" or error["type"] in _MODEL_LEVEL_FIELDS:
        return str(error["msg"])
    if error["type"] == "missing" or (
        error["type"] in ("string_type", "model_type", "dict_type") and error.get("input") is None
    ):
        return MSG_REQUIRED
    return _PYDANTIC_MESSAGES.get(error["type"], str(error["msg"]))


def _path(error: Any) -> str:
    loc = [str(part) for part in error["loc"]]
    if error["type"] in _MODEL_LEVEL_FIELDS:
        loc = [*loc, error["type"]]
    return ".".join(loc) or "__all__"


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Blank strings count as "not filled in" (so an empty input reports
    "required", not a parse error)."""
    return {key: _clean_value(value) for key, value in data.items()}


def _clean_value(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, dict):
        return _clean(value)
    return value


def validate_tab(
    tab: TabName, data: dict[str, Any] | None, context: ValidationContext
) -> tuple[_TabModel | None, dict[str, str]]:
    """Validates one tab. Returns `(model, {})` when it passes, else
    `(None, field_errors)`. Never raises."""
    model = TAB_MODELS[tab]
    try:
        parsed = model.model_validate(_clean(data or {}), context=context)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for error in exc.errors():
            errors.setdefault(_path(error), _message(error))
        return None, errors
    return parsed, {}


def context_for(
    data: dict[str, Any], known_metros: dict[str, frozenset[str]] | None = None
) -> ValidationContext:
    """Builds the cross-tab context from the draft's raw per-tab data."""
    you = data.get(TabName.YOU.value) or {}
    prop = data.get(TabName.PROPERTY.value) or {}
    first = str(you.get("first_name") or "").strip()
    last = str(you.get("last_name") or "").strip()
    full_name = f"{first} {last}" if first and last else None
    occupancy = prop.get("occupancy")
    return ValidationContext(
        occupancy=occupancy if isinstance(occupancy, str) else None,
        full_name=full_name,
        known_metros=known_metros or {},
    )


def validate_all(
    data: dict[str, Any], context: ValidationContext
) -> tuple[dict[TabName, _TabModel], dict[TabName, dict[str, str]]]:
    """Validates every tab: `(parsed models, {tab: field_errors})` -- the
    second dict only holds tabs that fail."""
    parsed: dict[TabName, _TabModel] = {}
    failures: dict[TabName, dict[str, str]] = {}
    for tab in TAB_ORDER:
        model, errors = validate_tab(tab, data.get(tab.value), context)
        if model is None:
            failures[tab] = errors
        else:
            parsed[tab] = model
    return parsed, failures


def first_incomplete_tab(failures: dict[TabName, dict[str, str]]) -> TabName:
    for tab in TAB_ORDER:
        if tab in failures:
            return tab
    return TabName.CONSENT
