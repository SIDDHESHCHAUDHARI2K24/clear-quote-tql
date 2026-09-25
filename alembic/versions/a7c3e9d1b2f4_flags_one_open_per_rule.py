"""flags: one open row per (application, field, rule)

CQ-028a review M1: concurrent edits could insert two unresolved `flags`
rows for the same `(application_id, field_key, rule)`, after which
`write_flag`/`resolve_flag` fail with `MultipleResultsFound`. The writers
now serialise on the application row lock; this partial unique index is
the backstop. Existing duplicates are cleaned first, keeping the oldest
open row (the extra rows are deleted, not resolved, so the timeline does
not gain resolutions that never happened).

Revision ID: a7c3e9d1b2f4
Revises: f1a2b3c4d5e6
Create Date: 2026-09-25 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d1b2f4"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_flags_open_application_field_rule"


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM flags
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY application_id, field_key, rule
                           ORDER BY created_at, id
                       ) AS rn
                FROM flags
                WHERE resolved_at IS NULL
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    )
    op.create_index(
        INDEX_NAME,
        "flags",
        ["application_id", "field_key", "rule"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="flags")
