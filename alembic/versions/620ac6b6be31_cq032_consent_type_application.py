"""cq032 consent type application

CQ-032 (plan.md decision 18): the apply wizard records its tab-4 consent
(soft-pull authorization, contact consent, terms) as one `consents` row
of the new type `application`.

`ALTER TYPE ... ADD VALUE` cannot be undone in place, so the downgrade
deletes the `application` rows and rebuilds the enum without the value.

Revision ID: 620ac6b6be31
Revises: 3b55187d53d7
Create Date: 2026-09-25 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "620ac6b6be31"
down_revision: Union[str, None] = "3b55187d53d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE consent_type ADD VALUE IF NOT EXISTS 'application'")


def downgrade() -> None:
    op.execute("DELETE FROM consents WHERE type = 'application'")
    op.execute("ALTER TYPE consent_type RENAME TO consent_type_old")
    op.execute("CREATE TYPE consent_type AS ENUM ('hard_pull')")
    op.execute(
        "ALTER TABLE consents ALTER COLUMN type TYPE consent_type "
        "USING type::text::consent_type"
    )
    op.execute("DROP TYPE consent_type_old")
