"""multi_account_user_seller_access

Revision ID: c3f81a920b44
Revises: 08c6a96e1502
Create Date: 2026-06-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c3f81a920b44'
down_revision = '08c6a96e1502'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_seller_access',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('seller_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='admin'),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id', 'seller_id'),
    )

    # Migrate existing 1:1 pairs from users.seller_id into the new table
    op.execute("""
        INSERT INTO user_seller_access (user_id, seller_id, role, granted_at)
        SELECT id, seller_id, 'admin', now()
        FROM users
        WHERE seller_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    op.drop_constraint('users_seller_id_fkey', 'users', type_='foreignkey')
    op.drop_column('users', 'seller_id')


def downgrade() -> None:
    op.add_column('users', sa.Column('seller_id', sa.UUID(), nullable=True))
    op.create_foreign_key('users_seller_id_fkey', 'users', 'sellers', ['seller_id'], ['id'])

    # Restore: pick one seller_id per user (the first one found)
    op.execute("""
        UPDATE users u
        SET seller_id = (
            SELECT seller_id FROM user_seller_access
            WHERE user_id = u.id
            ORDER BY granted_at ASC
            LIMIT 1
        )
    """)

    op.drop_table('user_seller_access')
