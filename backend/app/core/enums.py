"""Cross-cutting enums shared by multiple features.

Kept here (rather than beside a single owning model) to avoid circular
imports between features that share a status/severity/source vocabulary —
e.g. `applications` and `quotes/send` both need `ApplicationStatus`-adjacent
concepts, and `verification` needs `FieldSource` which `field_values` rows
from every other feature reference.

Feature-specific enums (e.g. `PartyRole`, `HousingStatus`) live beside their
owning model instead — see `docs/backlog/CQ-007-data-model/spec.md`.

All values are lower_snake_case strings; every enum is rendered as a native
Postgres enum type (`native_enum=True`, SQLAlchemy's default for `Enum`).
"""

import enum


class UserRole(enum.StrEnum):
    LO = "lo"
    MANAGER = "manager"
    ADMIN = "admin"


class ApplicationStatus(enum.StrEnum):
    """Mirrors the application status machine in `system-design.md`,
    including the terminal `withdrawn`/`closed` states set by the LO."""

    INTAKE = "intake"
    VERIFYING = "verifying"
    NEEDS_ATTENTION = "needs_attention"
    READY_TO_PRICE = "ready_to_price"
    PRICED = "priced"
    SENT = "sent"
    VIEWED = "viewed"
    OPTION_SELECTED = "option_selected"
    INQUIRY = "inquiry"
    STALE = "stale"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"


class Occupancy(enum.StrEnum):
    """Per override O2: Primary, LTR or STR only — no `second_home`."""

    PRIMARY = "primary"
    INVESTMENT = "investment"


class Strategy(enum.StrEnum):
    """Null on `applications.strategy` when `occupancy = primary`."""

    LTR = "ltr"
    STR = "str"


class LoanPurpose(enum.StrEnum):
    """Single member per override O1 (Purchase only); kept as an enum
    rather than a bool so refinance can be added later without a column
    type change."""

    PURCHASE = "purchase"


class FieldSource(enum.StrEnum):
    """Drives the source badge + "revert to source" UI on `field_values`."""

    ENCOMPASS = "encompass"
    RENTCAST = "rentcast"
    AIRDNA = "airdna"
    SMARTASSET = "smartasset"
    STEADILY = "steadily"
    OPTIMAL_BLUE = "optimal_blue"
    CREDIT_BUREAU = "credit_bureau"
    PROPERTY_SEARCH = "property_search"
    LO_ENTRY = "lo_entry"
    FORMULA = "formula"
    DEFAULT = "default"
    LO_OVERRIDE = "lo_override"


class ApplicationTab(enum.StrEnum):
    """Matches the 7 workspace tabs."""

    BORROWERS = "borrowers"
    HOUSING = "housing"
    CREDIT = "credit"
    ASSETS = "assets"
    PROPERTY = "property"
    PRICING = "pricing"
    SEND = "send"


class FlagSeverity(enum.StrEnum):
    """Decision: `blocking` halts pipeline progression (Verifying ->
    NeedsAttention) and blocks Send; `warning` is a visible tab count only;
    `info` is reserved for auto-fix outcomes and never becomes a `flags`
    row."""

    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"
