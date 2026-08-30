"""add_device_fingerprinting_to_refresh_tokens

Revision ID: 12a7942e3290
Revises: a2d850ed45df
Create Date: 2026-08-30 02:31:22.216127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12a7942e3290'
down_revision: Union[str, Sequence[str], None] = 'a2d850ed45df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'refresh_tokens',
        sa.Column('ip_address', sa.String(length=45), nullable=True),
    )
    op.add_column(
        'refresh_tokens',
        sa.Column('user_agent', sa.String(length=512), nullable=True),
    )
    op.add_column(
        'refresh_tokens',
        sa.Column('device_name', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'refresh_tokens',
        sa.Column('location', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'refresh_tokens',
        sa.Column(
            'last_seen_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('refresh_tokens', 'last_seen_at')
    op.drop_column('refresh_tokens', 'location')
    op.drop_column('refresh_tokens', 'device_name')
    op.drop_column('refresh_tokens', 'user_agent')
    op.drop_column('refresh_tokens', 'ip_address')
