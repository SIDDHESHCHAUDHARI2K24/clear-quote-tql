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


async def test_every_fk_column_has_an_index(test_engine: AsyncEngine) -> None:
    """Review finding #2: every FK column must be indexed (spec.md
    "Conventions (all tables)": "Every FK column is indexed").

    Inspects the live, migrated DB rather than the ORM models, so this
    catches a migration that doesn't actually create the index a model
    declares (or vice versa) — not just a model-level typo.
    """

    def _fk_columns_without_an_index(sync_conn: sa.Connection) -> dict[str, list[str]]:
        inspector = sa.inspect(sync_conn)
        missing: dict[str, list[str]] = {}

        for table_name in inspector.get_table_names():
            if table_name == "alembic_version":
                continue

            fk_columns = {
                column
                for fk in inspector.get_foreign_keys(table_name)
                for column in fk["constrained_columns"]
            }
            if not fk_columns:
                continue

            # A column is "covered" if it's the primary key, the leading
            # column of a unique constraint, or the leading column of any
            # index — Postgres (like most DBs) can use any of those to
            # satisfy a lookup on that column, same leftmost-prefix rule a
            # composite index would give it.
            covered_columns: set[str] = set(
                inspector.get_pk_constraint(table_name).get("constrained_columns") or []
            )
            for unique in inspector.get_unique_constraints(table_name):
                if unique["column_names"] and unique["column_names"][0]:
                    covered_columns.add(unique["column_names"][0])
            for index in inspector.get_indexes(table_name):
                if index["column_names"] and index["column_names"][0]:
                    covered_columns.add(index["column_names"][0])

            uncovered = sorted(fk_columns - covered_columns)
            if uncovered:
                missing[table_name] = uncovered

        return missing

    async with test_engine.connect() as conn:
        missing = await conn.run_sync(_fk_columns_without_an_index)

    assert missing == {}, f"FK columns without an index: {missing}"


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
