"""p5p6 foundation

P5/P6 foundation unit (docs/backlog/phase-p5-p6-foundation.md,
phase-p5-p6-plan.md E1/E8/E14): the one shared migration every P5
(CQ-025-030) and P6 (CQ-031-034) item was predicted to need, landed once
up front so parallel worker worktrees never fork `alembic heads`.

- `flags.message` (text, nullable): human-readable flag text (E8),
  backfilled below from the rule ids (a frozen copy of
  `verification/rules.py::flag_message` at the time of writing).
- `consents`: `status` (`consent_status` enum; existing rows -> `accepted`),
  `requested_by` (FK users, indexed), `requested_at`, `decided_at`,
  `expires_at`, `typed_name`, `user_agent`, `text_version`,
  `decline_reason`; `text_hash`/`ip`/`at` become nullable so a pending
  request row (CQ-028 "Request hard pull") can exist before a decision.
- `support_requests` (CQ-034).
- `application_drafts` (CQ-032), one open draft per borrower via the
  partial unique index `uq_application_drafts_open_per_borrower`.
- `applications.source` (`application_source` enum `los`/`portal`,
  default `los`, not null): the pipeline skips `import_application` for
  `portal` rows (E14).

Revision ID: 3b55187d53d7
Revises: e419a34bcdbd
Create Date: 2026-09-25 11:16:17.615504

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3b55187d53d7"
down_revision: Union[str, None] = "e419a34bcdbd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

application_source = postgresql.ENUM("los", "portal", name="application_source", create_type=False)
consent_status = postgresql.ENUM(
    "pending", "accepted", "declined", "expired", name="consent_status", create_type=False
)

# Frozen copy of `rules.py::RULE_MESSAGES` for the backfill (a migration
# must not import app code that may change later).
_FLAG_MESSAGE_BACKFILL = """
UPDATE flags SET message = CASE rule
    WHEN 'ob_required_field' THEN 'Cannot price: missing ' || CASE field_key
        WHEN 'occupancy_type' THEN 'Occupancy'
        WHEN 'RepresentativeFICO' THEN 'Representative FICO'
        ELSE regexp_replace(field_key, '([a-z])([A-Z])', '\\1 \\2', 'g')
    END
    WHEN 'housing_history_24mo'
        THEN 'Less than 24 months of housing history on file; add a prior address.'
    WHEN 'ssn_format' THEN 'SSN must be exactly 9 digits.'
    WHEN 'dob_format' THEN 'Date of birth is missing or not in the past.'
    WHEN 'assets_vs_ctc_reserves'
        THEN 'Verified assets are below cash to close plus required reserves.'
    WHEN 'dti_primary' THEN 'DTI exceeds the 45% guideline.'
    WHEN 'dscr_bucket_unstable'
        THEN 'DSCR bucket changed between pricing passes; priced at the lower DSCR.'
    ELSE 'Check ' || replace(field_key, '_', ' ') || '.'
END
WHERE message IS NULL
"""


def upgrade() -> None:
    bind = op.get_bind()
    application_source.create(bind, checkfirst=True)
    consent_status.create(bind, checkfirst=True)

    op.create_table(
        "application_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("borrower_account_id", sa.UUID(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("current_tab", sa.String(), server_default="you", nullable=False),
        sa.Column("submitted_application_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["borrower_account_id"], ["borrower_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["submitted_application_id"], ["applications.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_drafts_borrower_account_id"),
        "application_drafts",
        ["borrower_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_drafts_submitted_application_id"),
        "application_drafts",
        ["submitted_application_id"],
        unique=False,
    )
    op.create_index(
        "uq_application_drafts_open_per_borrower",
        "application_drafts",
        ["borrower_account_id"],
        unique=True,
        postgresql_where=sa.text("submitted_application_id IS NULL"),
    )

    op.create_table(
        "support_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("reference", sa.String(length=16), nullable=False),
        sa.Column("borrower_account_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("preferred_contact", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["borrower_account_id"], ["borrower_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index(
        op.f("ix_support_requests_application_id"),
        "support_requests",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_requests_borrower_account_id"),
        "support_requests",
        ["borrower_account_id"],
        unique=False,
    )

    op.add_column(
        "applications",
        sa.Column("source", application_source, server_default="los", nullable=False),
    )

    op.add_column(
        "consents",
        sa.Column("status", consent_status, server_default="accepted", nullable=False),
    )
    op.add_column("consents", sa.Column("requested_by", sa.UUID(), nullable=True))
    op.add_column("consents", sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("consents", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("consents", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("consents", sa.Column("text_version", sa.String(), nullable=True))
    op.add_column("consents", sa.Column("typed_name", sa.String(), nullable=True))
    op.add_column("consents", sa.Column("user_agent", sa.Text(), nullable=True))
    op.add_column("consents", sa.Column("decline_reason", sa.Text(), nullable=True))
    op.alter_column("consents", "text_hash", existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column("consents", "ip", existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column(
        "consents", "at", existing_type=postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    op.create_index(op.f("ix_consents_requested_by"), "consents", ["requested_by"], unique=False)
    op.create_foreign_key(
        "consents_requested_by_fkey",
        "consents",
        "users",
        ["requested_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Pre-existing rows are recorded decisions: their decision time is `at`.
    op.execute("UPDATE consents SET decided_at = at WHERE decided_at IS NULL")

    op.add_column("flags", sa.Column("message", sa.Text(), nullable=True))
    op.execute(_FLAG_MESSAGE_BACKFILL)


def downgrade() -> None:
    op.drop_column("flags", "message")

    op.drop_constraint("consents_requested_by_fkey", "consents", type_="foreignkey")
    op.drop_index(op.f("ix_consents_requested_by"), table_name="consents")
    # Pending/declined rows have no decision data; they cannot survive the
    # old NOT NULL columns.
    op.execute("DELETE FROM consents WHERE text_hash IS NULL OR ip IS NULL OR at IS NULL")
    op.alter_column(
        "consents", "at", existing_type=postgresql.TIMESTAMP(timezone=True), nullable=False
    )
    op.alter_column("consents", "ip", existing_type=sa.VARCHAR(), nullable=False)
    op.alter_column("consents", "text_hash", existing_type=sa.VARCHAR(), nullable=False)
    for column in (
        "decline_reason",
        "user_agent",
        "typed_name",
        "text_version",
        "expires_at",
        "decided_at",
        "requested_at",
        "requested_by",
        "status",
    ):
        op.drop_column("consents", column)

    op.drop_column("applications", "source")

    op.drop_index(op.f("ix_support_requests_borrower_account_id"), table_name="support_requests")
    op.drop_index(op.f("ix_support_requests_application_id"), table_name="support_requests")
    op.drop_table("support_requests")

    op.drop_index(
        "uq_application_drafts_open_per_borrower",
        table_name="application_drafts",
        postgresql_where=sa.text("submitted_application_id IS NULL"),
    )
    op.drop_index(
        op.f("ix_application_drafts_submitted_application_id"), table_name="application_drafts"
    )
    op.drop_index(
        op.f("ix_application_drafts_borrower_account_id"), table_name="application_drafts"
    )
    op.drop_table("application_drafts")

    bind = op.get_bind()
    consent_status.drop(bind, checkfirst=True)
    application_source.drop(bind, checkfirst=True)
