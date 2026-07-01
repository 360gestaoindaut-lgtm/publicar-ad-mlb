"""add_image_engine_state

Revision ID: b7e4a1c92f83
Revises: fbf3f83bf9e4
Create Date: 2026-07-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b7e4a1c92f83'
down_revision = 'fbf3f83bf9e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'image_engine_state',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('current_engine', sa.String(length=20), nullable=False, server_default='openai'),
        sa.Column('last_openai_error', sa.String(length=500), nullable=True),
        sa.Column('last_switch_to_openai_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "INSERT INTO image_engine_state (id, current_engine, updated_at) "
        "VALUES (gen_random_uuid(), 'openai', now())"
    )


def downgrade() -> None:
    op.drop_table('image_engine_state')
