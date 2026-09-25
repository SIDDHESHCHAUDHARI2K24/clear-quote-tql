"""cq020 send tracking

CQ-020 (plan.md Decisions 7-8): `quote_packages.send_workflow_id` /
`send_status` / `send_error` back the poll-able `GET /send-status`;
`quote_package_versions.send_workflow_id` (unique) and `outbox_email_id`
are the idempotency keys of the `SendQuotePackage` activities.

Revision ID: d4a1c0f2e920
Revises: c8869567cd57
Create Date: 2026-09-25 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4a1c0f2e920"
down_revision: Union[str, None] = "c8869567cd57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quote_packages", sa.Column("send_workflow_id", sa.String(), nullable=True))
    op.add_column("quote_packages", sa.Column("send_status", sa.String(), nullable=True))
    op.add_column("quote_packages", sa.Column("send_error", sa.Text(), nullable=True))
    op.add_column(
        "quote_package_versions", sa.Column("send_workflow_id", sa.String(), nullable=True)
    )
    op.create_unique_constraint(
        "uq_quote_package_versions_send_workflow_id",
        "quote_package_versions",
        ["send_workflow_id"],
    )
    op.add_column(
        "quote_package_versions",
        sa.Column("outbox_email_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quote_package_versions_outbox_email_id",
        "quote_package_versions",
        "outbox_emails",
        ["outbox_email_id"],
        ["id"],
    )
    op.create_index(
        "ix_quote_package_versions_outbox_email_id",
        "quote_package_versions",
        ["outbox_email_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_quote_package_versions_outbox_email_id", "quote_package_versions")
    op.drop_constraint(
        "fk_quote_package_versions_outbox_email_id", "quote_package_versions", type_="foreignkey"
    )
    op.drop_column("quote_package_versions", "outbox_email_id")
    op.drop_constraint(
        "uq_quote_package_versions_send_workflow_id", "quote_package_versions", type_="unique"
    )
    op.drop_column("quote_package_versions", "send_workflow_id")
    op.drop_column("quote_packages", "send_error")
    op.drop_column("quote_packages", "send_status")
    op.drop_column("quote_packages", "send_workflow_id")
