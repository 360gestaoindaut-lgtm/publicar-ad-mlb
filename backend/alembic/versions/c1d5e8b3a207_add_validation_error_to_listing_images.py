"""add_validation_error_to_listing_images

Guarda o motivo da reprovação no QA de imagem (status="validation_failed").

Revision ID: c1d5e8b3a207
Revises: a3f7c9d2e841
Create Date: 2026-08-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d5e8b3a207'
down_revision = 'a3f7c9d2e841'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'listing_images',
        sa.Column('validation_error', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('listing_images', 'validation_error')
