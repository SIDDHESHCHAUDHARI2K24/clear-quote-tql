"""seed settings defaults

Data-only migration (not part of `initial_schema`, and not `make demo-reset`
persona seed data — CQ-010's scope). Inserts the default `settings` rows
every later item's `quote_engine`/pricing/verification logic reads, per
`docs/backlog/CQ-007-data-model/spec.md`.

Revision ID: 8aa99c7f2577
Revises: 4864c0fa0754
Create Date: 2026-09-25 01:17:22.138318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '8aa99c7f2577'
down_revision: Union[str, None] = '4864c0fa0754'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


settings_table = sa.table(
    "settings",
    sa.column("key", sa.String),
    sa.column("value", JSONB),
    sa.column("description", sa.String),
)

DEFAULTS: list[dict[str, object]] = [
    {"key": "fee_lender_processing", "value": 995.00, "description": "Lender processing fee ($)"},
    {"key": "fee_lender_underwriting", "value": 795.00, "description": "Lender underwriting fee ($)"},
    {"key": "title_pct", "value": 0.007, "description": "Title/escrow fee, % of purchase price"},
    {"key": "str_expense_ratio", "value": 0.20, "description": "STR operating expense ratio"},
    {"key": "insurance_default_pct", "value": 0.005, "description": "Default annual insurance rate, % of price"},
    {"key": "land_allocation_pct", "value": 0.20, "description": "Cost-seg land allocation, % of basis"},
    {"key": "accelerated_property_pct", "value": 0.25, "description": "Cost-seg accelerated-property allocation, % of basis"},
    {"key": "bonus_depreciation_pct", "value": 1.00, "description": "Bonus depreciation rate on accelerated basis"},
    {"key": "investor_marginal_tax_rate", "value": 0.32, "description": "Assumed investor marginal tax rate for tax-savings estimate"},
    {"key": "prepaid_interest_days", "value": 15, "description": "Prepaid interest, days"},
    {"key": "prepaid_insurance_months", "value": 14, "description": "Prepaid insurance escrow, months"},
    {"key": "prepaid_tax_months", "value": 3, "description": "Prepaid property tax escrow, months"},
    {"key": "reserves_months_primary", "value": 2, "description": "Required reserves, months (primary occupancy)"},
    {"key": "reserves_months_investment", "value": 6, "description": "Required reserves, months (investment occupancy)"},
    {"key": "stale_quote_days", "value": 21, "description": "Days after pricing before a quote is flagged stale"},
    {"key": "report_link_expiry_days", "value": 7, "description": "Borrower report magic-link expiry, days"},
]


def upgrade() -> None:
    op.bulk_insert(settings_table, DEFAULTS)


def downgrade() -> None:
    keys = tuple(row["key"] for row in DEFAULTS)
    op.execute(sa.text("DELETE FROM settings WHERE key IN :keys").bindparams(
        sa.bindparam("keys", value=keys, expanding=True)
    ))
