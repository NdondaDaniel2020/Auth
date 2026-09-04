"""audit_logs append only and hash chain

Revision ID: e8b9c0d1e2f3
Revises: 12a7942e3290
Create Date: 2026-09-04 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = '12a7942e3290'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'audit_logs',
        sa.Column('previous_hash', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'audit_logs',
        sa.Column(
            'hash', sa.String(length=64), nullable=False, server_default=''
        ),
    )
    op.create_index(
        'ix_audit_logs_hash',
        'audit_logs',
        ['hash'],
        unique=False,
    )

    op.execute(
        """
        DO $$
        BEGIN
            CREATE OR REPLACE FUNCTION block_audit_log_mutation()
            RETURNS TRIGGER AS $func$
            BEGIN
                RAISE EXCEPTION 'A tabela audit_logs é append-only. Operações de UPDATE ou DELETE são proibidas.';
            END;
            $func$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS prevent_audit_log_mutation ON audit_logs;
            CREATE TRIGGER prevent_audit_log_mutation
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION block_audit_log_mutation();
        EXCEPTION
            WHEN undefined_function THEN
                NULL;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                REVOKE ALL ON TABLE audit_logs FROM app_user;
                GRANT INSERT, SELECT ON TABLE audit_logs TO app_user;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            DROP TRIGGER IF EXISTS prevent_audit_log_mutation ON audit_logs;
            DROP FUNCTION IF EXISTS block_audit_log_mutation();
        EXCEPTION
            WHEN undefined_function THEN
                NULL;
        END $$;
        """
    )
    op.drop_index('ix_audit_logs_hash', table_name='audit_logs')
    op.drop_column('audit_logs', 'hash')
    op.drop_column('audit_logs', 'previous_hash')
