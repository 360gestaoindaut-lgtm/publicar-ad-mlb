"""add_product_id_to_listings

Revision ID: b8d2f4a6c0e1
Revises: a9c1e3b5d7f0
Create Date: 2026-06-21 21:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b8d2f4a6c0e1'
down_revision = 'a9c1e3b5d7f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'listings',
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id'), nullable=True),
    )
    op.create_index('idx_listings_product_id', 'listings', ['product_id'])


def downgrade() -> None:
    op.drop_index('idx_listings_product_id', table_name='listings')
    op.drop_column('listings', 'product_id')
