"""quote_package_versions expired_at

CQ-030 (stale quote job, plan.md decision #1): the `mark_stale` job
stamps `expired_at` once, with the run's injected `now`, on every sent
version whose `expires_at` has passed. That makes "expired" queryable
(the dashboard's stale list, the admin job's counts) and makes the step
idempotent. The borrower report (CQ-022) still computes `expired` from
`expires_at` at request time.

Revision ID: c30a57a1e0d1
Revises: 3b55187d53d7
Create Date: 2026-09-25 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c30a57a1e0d1'
down_revision: Union[str, None] = '3b55187d53d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'quote_package_versions',
        sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_quote_package_versions_expired_at',
        'quote_package_versions',
        ['expired_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_quote_package_versions_expired_at', table_name='quote_package_versions')
    op.drop_column('quote_package_versions', 'expired_at')
