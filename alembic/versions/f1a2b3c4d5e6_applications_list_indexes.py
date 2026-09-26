"""applications list indexes

CQ-027 (Applications list, spec.md AC5 "under 300 ms"): three indexes the
listing endpoint's filters and default sort need that nothing before it
added --

- `ix_applications_updated_at`: the default `sort=-updated_at`.
- `ix_applications_created_at`: `created_from`/`created_to`.
- `ix_applications_requested_price`: `amount_min`/`amount_max` and
  `sort=amount`/`-amount`.

`lo_id`, `status` and `client_id` are already indexed on `applications`
(CQ-007/CQ-010); `flags` already has `ix_flags_application_id_resolved_at`
(CQ-007) for the open-flag-count subquery.

Revision ID: f1a2b3c4d5e6
Revises: 3b55187d53d7
Create Date: 2026-09-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "3b55187d53d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_applications_updated_at", "applications", ["updated_at"], unique=False
    )
    op.create_index(
        "ix_applications_created_at", "applications", ["created_at"], unique=False
    )
    op.create_index(
        "ix_applications_requested_price", "applications", ["requested_price"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_applications_requested_price", table_name="applications")
    op.drop_index("ix_applications_created_at", table_name="applications")
    op.drop_index("ix_applications_updated_at", table_name="applications")
