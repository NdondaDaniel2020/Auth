"""mfa readiness: user flags and mfa_methods table

Revision ID: b1c2d3e4f5a6
Revises: f7a8b9c0d1e2
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), server_default=sa.text('(false())'), nullable=False))
    op.add_column('users', sa.Column('mfa_type', sa.String(length=16), nullable=True))

    op.create_table('mfa_methods',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('secret', sa.String(length=512), nullable=True),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(false())'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mfa_methods_user_id', 'mfa_methods', ['user_id'], unique=False)
    op.create_index('ix_mfa_methods_user_type', 'mfa_methods', ['user_id', 'type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_mfa_methods_user_type', table_name='mfa_methods')
    op.drop_index('ix_mfa_methods_user_id', table_name='mfa_methods')
    op.drop_table('mfa_methods')

    op.drop_column('users', 'mfa_type')
    op.drop_column('users', 'mfa_enabled')
