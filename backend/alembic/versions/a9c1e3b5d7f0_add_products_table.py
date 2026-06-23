"""add_products_table

Revision ID: a9c1e3b5d7f0
Revises: f4a2e9d10b83
Create Date: 2026-06-21 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a9c1e3b5d7f0'
down_revision = 'f4a2e9d10b83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('seller_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sellers.id'), nullable=False),
        sa.Column('sku', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('brand', sa.String(200), nullable=True),
        sa.Column('ean', sa.String(20), nullable=True),
        sa.Column('ncm', sa.String(10), nullable=True),
        sa.Column('fiscal_origin', sa.SmallInteger(), nullable=True),
        sa.Column('icms_cst', sa.String(4), nullable=True),
        sa.Column('icms_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('pis_cst', sa.String(4), nullable=True),
        sa.Column('cofins_cst', sa.String(4), nullable=True),
        sa.Column('weight_kg', sa.Numeric(10, 3), nullable=True),
        sa.Column('length_cm', sa.Integer(), nullable=True),
        sa.Column('width_cm', sa.Integer(), nullable=True),
        sa.Column('height_cm', sa.Integer(), nullable=True),
        sa.Column('acquisition_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('seller_id', 'sku', name='uq_products_seller_sku'),
    )
    op.create_index('idx_products_seller_id', 'products', ['seller_id'])


def downgrade() -> None:
    op.drop_index('idx_products_seller_id', table_name='products')
    op.drop_table('products')
