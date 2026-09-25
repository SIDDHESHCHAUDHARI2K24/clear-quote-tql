"""applications occupancy nullable

CQ-010 review round 1, finding #1 (orchestrator-approved schema change):
`applications.occupancy` was non-nullable, so persona 7 (Aisha Coleman)'s
"occupancy_type null in LOS record" defect could never propagate past
`import_from_los` -- `applications.occupancy` was always LO-entered at
intake, before import ever ran. Making it nullable lets `import_from_los`
copy occupancy from the LOS record itself, leaving it `NULL` when that
record's `occupancy_type` is missing, so the pipeline's Validate stage can
correctly raise "Cannot price: missing Occupancy" (system-design.md,
this item's own spec.md, and CQ-012's spec.md all pin this exact wording).

`applications.strategy` was already nullable (CQ-007) -- no change needed
there.

Revision ID: e7b20ff388a7
Revises: 8aa99c7f2577
Create Date: 2026-09-25 03:42:01.167012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b20ff388a7'
down_revision: Union[str, None] = '8aa99c7f2577'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OCCUPANCY_ENUM = sa.Enum('primary', 'investment', name='occupancy')


def upgrade() -> None:
    op.alter_column(
        'applications',
        'occupancy',
        existing_type=_OCCUPANCY_ENUM,
        nullable=True,
    )


def downgrade() -> None:
    # Any row with occupancy still NULL (e.g. a never-imported persona 7)
    # must be backfilled before this can succeed -- deliberately not
    # automatic, since picking a value here would be a silent data change.
    op.alter_column(
        'applications',
        'occupancy',
        existing_type=_OCCUPANCY_ENUM,
        nullable=False,
    )
