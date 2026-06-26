"""spec013 product fields and seller title configs

Revision ID: 2dc754f932f4
Revises: d3aa35ba6d71
Create Date: 2026-06-26 11:57:23.110807

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '2dc754f932f4'
down_revision = 'd3aa35ba6d71'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New optional columns on products
    op.add_column("products", sa.Column("product_group", sa.String(100), nullable=True))
    op.add_column("products", sa.Column("technical_reference", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("vehicle_application", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("color", sa.String(100), nullable=True))
    op.add_column("products", sa.Column("size", sa.String(50), nullable=True))
    op.add_column("products", sa.Column("capacity", sa.String(50), nullable=True))
    op.add_column("products", sa.Column("material", sa.String(100), nullable=True))
    op.add_column("products", sa.Column("gender", sa.String(20), nullable=True))

    # seller_title_configs table
    op.create_table(
        "seller_title_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_group", sa.String(100), nullable=False),
        sa.Column("title_structure", sa.Text(), nullable=False),
        sa.Column("title_rules", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("seller_id", "product_group", name="uq_seller_title_config_group"),
    )
    op.create_index("ix_seller_title_configs_seller_id", "seller_title_configs", ["seller_id"])


def downgrade() -> None:
    op.drop_table("seller_title_configs")
    for col in ["product_group", "technical_reference", "vehicle_application",
                "color", "size", "capacity", "material", "gender"]:
        op.drop_column("products", col)
