
"""sprint2_product_image_batch_import

Revision ID: d9e02b741f35
Revises: c3f81a920b44
Create Date: 2026-06-21 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd9e02b741f35'
down_revision = 'c3f81a920b44'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'product_images',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('seller_id', sa.UUID(), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=False),
        sa.Column('ml_picture_id', sa.String(length=100), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='gemini'),
        sa.Column('is_approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_product_images_seller_sku', 'product_images', ['seller_id', 'sku'])

    op.create_table(
        'batch_imports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('seller_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_batch_imports_seller_id', 'batch_imports', ['seller_id'])

    op.create_table(
        'batch_import_rows',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('batch_id', sa.UUID(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=False),
        sa.Column('listing_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['batch_id'], ['batch_imports.id']),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_batch_import_rows_batch_id', 'batch_import_rows', ['batch_id'])


def downgrade() -> None:
    op.drop_table('batch_import_rows')
    op.drop_table('batch_imports')
    op.drop_index('ix_product_images_seller_sku', table_name='product_images')
    op.drop_table('product_images')
