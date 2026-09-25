"""AC2/AC3/AC7: the full schema exists with the documented tables and enums.

This test module explicitly imports every feature/integration `models.py`
itself (the same requirement `alembic/env.py` has) rather than relying on
other test modules happening to import them first — pytest test-collection
order is not something this test should depend on.
"""

import enum

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

import app.features.applications.assets.models  # noqa: F401
import app.features.applications.credit.models  # noqa: F401
import app.features.applications.timeline.models  # noqa: F401
import app.features.applications.verification.models  # noqa: F401
import app.features.auth.models  # noqa: F401
import app.features.clients.models  # noqa: F401
import app.features.pricing.scenarios.models  # noqa: F401
import app.features.quotes.builder.models  # noqa: F401
import app.features.settings.models  # noqa: F401
import app.integrations.common.models  # noqa: F401
import app.integrations.crm.models  # noqa: F401
import app.integrations.insurance.models  # noqa: F401
import app.integrations.los.models  # noqa: F401
import app.integrations.rent.models  # noqa: F401
import app.integrations.str.models  # noqa: F401
import app.integrations.tax.models  # noqa: F401
from app.core.db import Base
from app.core.enums import (
    ApplicationStatus,
    ApplicationTab,
    FieldSource,
    FlagSeverity,
    LoanPurpose,
    Occupancy,
    Strategy,
    UserRole,
)
from app.features.applications.housing.models import HousingStatus
from app.features.applications.models import BusinessVesting, MaritalStatus, PartyRole
from app.features.applications.property.models import PropertyAddressStatus, PropertyType
from app.features.borrower.consent.models import ConsentType
from app.features.notifications.outbox.models import EmailStatus
from app.features.quotes.send.models import BorrowerAction
from app.integrations.credit.models import CreditPullType
from app.integrations.pricing.models import RateSheetProgram
from app.integrations.property_search.models import DealGrade

# Every table from `docs/backlog/CQ-007-data-model/spec.md`'s "Tables by
# owning module" section.
EXPECTED_TABLES = {
    "users",
    "borrower_accounts",
    "clients",
    "applications",
    "application_parties",
    "housing_history",
    "liabilities",
    "assets",
    "employment",
    "documents",
    "properties",
    "field_values",
    "flags",
    "activity_events",
    "scenarios",
    "quotes",
    "quote_packages",
    "consents",
    "outbox_emails",
    "settings",
    "provider_los_records",
    "provider_rate_sheet",
    "provider_rents",
    "provider_str_revenue",
    "provider_tax_rates",
    "provider_insurance_factors",
    "provider_listings",
    "provider_credit_reports",
    "crm_events",
    "integration_calls",
}

PROVIDER_TABLES = {
    "provider_los_records",
    "provider_rate_sheet",
    "provider_rents",
    "provider_str_revenue",
    "provider_tax_rates",
    "provider_insurance_factors",
    "provider_listings",
    "provider_credit_reports",
    "crm_events",
    "integration_calls",
}

ENUM_VALUES = {
    UserRole: {"lo", "manager", "admin"},
    ApplicationStatus: {
        "intake",
        "verifying",
        "needs_attention",
        "ready_to_price",
        "priced",
        "sent",
        "viewed",
        "option_selected",
        "inquiry",
        "stale",
        "withdrawn",
        "closed",
    },
    Occupancy: {"primary", "investment"},
    Strategy: {"ltr", "str"},
    LoanPurpose: {"purchase"},
    FieldSource: {
        "encompass",
        "rentcast",
        "airdna",
        "smartasset",
        "steadily",
        "optimal_blue",
        "credit_bureau",
        "property_search",
        "lo_entry",
        "formula",
        "default",
        "lo_override",
    },
    ApplicationTab: {"borrowers", "housing", "credit", "assets", "property", "pricing", "send"},
    FlagSeverity: {"info", "warning", "blocking"},
    PartyRole: {"borrower", "co_borrower"},
    MaritalStatus: {"married", "unmarried", "separated"},
    BusinessVesting: {"title_lien_in_llc", "personal_name"},
    HousingStatus: {"own", "rent", "rent_free"},
    PropertyAddressStatus: {"specific_address", "tbd"},
    PropertyType: {"single_family", "two_to_four_unit", "condo", "townhome"},
    BorrowerAction: {"option_selected", "inquiry"},
    ConsentType: {"hard_pull"},
    EmailStatus: {"queued", "sent", "failed"},
    RateSheetProgram: {"conventional", "dscr"},
    DealGrade: {"great_buy", "good_buy"},
    CreditPullType: {"soft_pull", "hard_pull"},
}


def test_all_tables_present() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_provider_tables_present() -> None:
    assert PROVIDER_TABLES <= set(Base.metadata.tables)


@pytest.mark.parametrize(("enum_cls", "expected_values"), list(ENUM_VALUES.items()))
def test_enum_values(enum_cls: type[enum.Enum], expected_values: set[str]) -> None:
    assert {member.value for member in enum_cls} == expected_values


async def test_application_status_enum_type_in_db_includes_withdrawn_and_closed(
    test_engine: AsyncEngine,
) -> None:
    """DB-side check (not just the Python enum) for the one enum the spec
    explicitly calls out: `ApplicationStatus` must include the terminal
    `withdrawn`/`closed` states in the actual Postgres enum type."""
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'application_status'"
            )
        )
        db_values = {row[0] for row in result}

    assert db_values == {member.value for member in ApplicationStatus}
    assert {"withdrawn", "closed"} <= db_values
