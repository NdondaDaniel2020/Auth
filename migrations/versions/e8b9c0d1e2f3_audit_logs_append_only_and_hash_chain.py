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
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.add_column(
            sa.Column('previous_hash', sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                'hash', sa.String(length=64), nullable=False, server_default=''
            )
        )
        batch_op.create_index(
            'ix_audit_logs_hash',
            ['hash'],
            unique=False,
        )

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(
            """
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
    elif bind.dialect.name == 'sqlite':
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_audit_log_update
            BEFORE UPDATE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'A tabela audit_logs é append-only. Operações de UPDATE são proibidas.');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_audit_log_delete
            BEFORE DELETE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'A tabela audit_logs é append-only. Operações de DELETE são proibidas.');
            END;
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(
            """
            DROP TRIGGER IF EXISTS prevent_audit_log_mutation ON audit_logs;
            DROP FUNCTION IF EXISTS block_audit_log_mutation();
            """
        )
    elif bind.dialect.name == 'sqlite':
        op.execute('DROP TRIGGER IF EXISTS prevent_audit_log_update;')
        op.execute('DROP TRIGGER IF EXISTS prevent_audit_log_delete;')

    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.drop_index('ix_audit_logs_hash')
        batch_op.drop_column('hash')
        batch_op.drop_column('previous_hash')

