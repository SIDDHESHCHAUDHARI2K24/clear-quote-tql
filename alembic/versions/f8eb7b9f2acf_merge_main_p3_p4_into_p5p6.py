"""merge main (P3/P4) into p5p6

P56-merge (docs/backlog/phase-p5-p6-main-merge-plan.md decision M2): joins
main's head `d4a1c0f2e920` (P3/P4) and phase-p5-p6's head `a7c3e9d1b2f4`
(P5/P6), which both branched from `e419a34bcdbd`. Schema-neutral: the two
lanes touch disjoint tables/columns, so no DDL is needed here and no
existing migration is edited.

Revision ID: f8eb7b9f2acf
Revises: d4a1c0f2e920, a7c3e9d1b2f4
Create Date: 2026-09-25 19:09:40.981773

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f8eb7b9f2acf"
down_revision: str | Sequence[str] | None = ("d4a1c0f2e920", "a7c3e9d1b2f4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
