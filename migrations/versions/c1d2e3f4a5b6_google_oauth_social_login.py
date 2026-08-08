"""google oauth: social login fields on users

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    ``hashed_password`` becomes nullable so OAuth-only users have no local
    password. SQLite requires a table rebuild for column alterations, so use
    batch mode there; other backends alter in place.
    """
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('users') as batch_op:
            batch_op.alter_column(
                'hashed_password',
                existing_type=sa.String(length=255),
                nullable=True,
            )
            batch_op.add_column(
                sa.Column('oauth_provider', sa.String(length=32), nullable=True)
            )
            batch_op.add_column(
                sa.Column('google_id', sa.String(length=255), nullable=True)
            )
    else:
        op.alter_column(
            'users',
            'hashed_password',
            existing_type=sa.String(length=255),
            nullable=True,
        )
        op.add_column(
            'users', sa.Column('oauth_provider', sa.String(length=32), nullable=True)
        )
        op.add_column(
            'users', sa.Column('google_id', sa.String(length=255), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_column('google_id')
            batch_op.drop_column('oauth_provider')
            batch_op.alter_column(
                'hashed_password',
                existing_type=sa.String(length=255),
                nullable=False,
            )
    else:
        op.drop_column('users', 'google_id')
        op.drop_column('users', 'oauth_provider')
        op.alter_column(
            'users',
            'hashed_password',
            existing_type=sa.String(length=255),
            nullable=False,
        )
