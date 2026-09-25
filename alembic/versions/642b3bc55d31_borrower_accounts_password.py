"""borrower_accounts_password

CQ-015: adds `password_hash` and `email_verified_at` to `borrower_accounts`
(spec.md scope). Both are nullable — `borrower/service.py::verify_otp` sets
both together on account creation, so a fully-migrated row never has one
without the other, but nullable keeps the migration itself column-only
(no backfill, no data migration).

Revision ID: 642b3bc55d31
Revises: 8aa99c7f2577
Create Date: 2026-09-25 03:08:27.877571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '642b3bc55d31'
down_revision: Union[str, None] = '8aa99c7f2577'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('borrower_accounts', sa.Column('password_hash', sa.String(), nullable=True))
    op.add_column(
        'borrower_accounts', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('borrower_accounts', 'email_verified_at')
    op.drop_column('borrower_accounts', 'password_hash')
