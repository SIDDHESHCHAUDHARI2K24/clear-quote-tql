"""flags: one open row per (application, field, rule)

CQ-028a review M1: concurrent edits could insert two unresolved `flags`
rows for the same `(application_id, field_key, rule)`, after which
`write_flag`/`resolve_flag` fail with `MultipleResultsFound`. The writers
now serialise on the application row lock; this partial unique index is
the backstop. Existing duplicates are cleaned first, keeping the oldest
open row (the extra rows are deleted, not resolved, so the timeline does
not gain resolutions that never happened).

It also backfills the `auto:borrower_home_phone` markers that `phone_copy`
now writes (see `upgrade`).

Revision ID: a7c3e9d1b2f4
Revises: c30a57a1e0d1
Create Date: 2026-09-25 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d1b2f4"
down_revision: Union[str, None] = "c30a57a1e0d1"
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
    # Backfill the `auto:borrower_home_phone` marker (review minor 3) for
    # data verified before `phone_copy` wrote it: the old heuristic (home
    # phone equals the cell phone, and no LO override) is the best signal
    # available for existing rows. New rows get the marker from the rule.
    op.execute(
        """
        INSERT INTO field_values (id, application_id, field_key, value, source)
        SELECT gen_random_uuid(), p.application_id, 'auto:borrower_home_phone',
               '"formula"'::jsonb, 'formula'
        FROM application_parties p
        WHERE p.role = 'borrower'
          AND p.home_phone IS NOT NULL
          AND p.home_phone = p.cell_phone
          AND NOT EXISTS (
              SELECT 1 FROM field_values f
              WHERE f.application_id = p.application_id
                AND f.field_key = 'orig:borrower_home_phone'
          )
        ON CONFLICT (application_id, field_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM field_values WHERE field_key LIKE 'auto:%'")
    op.drop_index(INDEX_NAME, table_name="flags")
