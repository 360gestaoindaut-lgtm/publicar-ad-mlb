"""add_seller_image_config_and_listing_image_i2i_columns

Revision ID: a3f7c9d2e841
Revises: b7e4a1c92f83
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a3f7c9d2e841'
down_revision = 'b7e4a1c92f83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'seller_image_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('seller_id', sa.UUID(), nullable=False),
        sa.Column('raw_base_url', sa.Text(), nullable=False),
        sa.Column('write_bucket_name', sa.String(length=200), nullable=True),
        sa.Column('write_endpoint_url', sa.Text(), nullable=True),
        sa.Column('write_access_key_id_enc', sa.Text(), nullable=True),
        sa.Column('write_secret_access_key_enc', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('seller_id', name='uq_seller_image_configs_seller_id'),
    )
    op.add_column('listing_images', sa.Column('kind', sa.String(length=20), nullable=False, server_default='individual'))
    op.add_column('listing_images', sa.Column('source_sku', sa.String(length=100), nullable=True))
    op.add_column('listing_images', sa.Column('r2_write_status', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('listing_images', 'r2_write_status')
    op.drop_column('listing_images', 'source_sku')
    op.drop_column('listing_images', 'kind')
    op.drop_table('seller_image_configs')
