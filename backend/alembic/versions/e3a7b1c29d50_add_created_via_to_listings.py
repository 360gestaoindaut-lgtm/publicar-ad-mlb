"""add_created_via_to_listings

Revision ID: e3a7b1c29d50
Revises: d9e02b741f35
Create Date: 2026-06-21 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e3a7b1c29d50'
down_revision = 'd9e02b741f35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'listings',
        sa.Column('created_via', sa.String(10), nullable=False, server_default='manual'),
    )


def downgrade() -> None:
    op.drop_column('listings', 'created_via')
