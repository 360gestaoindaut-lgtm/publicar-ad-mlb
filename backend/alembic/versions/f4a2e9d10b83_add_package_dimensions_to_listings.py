"""add_package_dimensions_to_listings

Revision ID: f4a2e9d10b83
Revises: e3a7b1c29d50
Create Date: 2026-06-21 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f4a2e9d10b83'
down_revision = 'e3a7b1c29d50'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('listings', sa.Column('package_weight_kg', sa.Numeric(10, 3), nullable=True))
    op.add_column('listings', sa.Column('package_length_cm', sa.Integer(), nullable=True))
    op.add_column('listings', sa.Column('package_width_cm', sa.Integer(), nullable=True))
    op.add_column('listings', sa.Column('package_height_cm', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('listings', 'package_height_cm')
    op.drop_column('listings', 'package_width_cm')
    op.drop_column('listings', 'package_length_cm')
    op.drop_column('listings', 'package_weight_kg')
