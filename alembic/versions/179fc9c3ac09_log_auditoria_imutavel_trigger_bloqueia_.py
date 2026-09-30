"""log_auditoria imutavel (trigger bloqueia update/delete - issue 83)

Revision ID: 179fc9c3ac09
Revises: 21145d4bb9be
Create Date: 2026-09-30 10:07:30.469980
"""
from typing import Sequence, Union

from alembic import op

revision: str = '179fc9c3ac09'
down_revision: Union[str, None] = '21145d4bb9be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Trigger que torna log_auditoria imutavel (auditoria e evidencia formal).
    # Impede UPDATE/DELETE em linha. TRUNCATE nao dispara BEFORE DELETE, entao
    # o create_all/lifespan e o db_clean dos testes continuam funcionando.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION lms.prevent_log_auditoria_modify()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'log_auditoria e imutavel: UPDATE/DELETE nao permitido';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_log_auditoria_immutable ON lms.log_auditoria
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_log_auditoria_immutable
        BEFORE UPDATE OR DELETE ON lms.log_auditoria
        FOR EACH ROW EXECUTE FUNCTION lms.prevent_log_auditoria_modify()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_log_auditoria_immutable ON lms.log_auditoria")
    op.execute("DROP FUNCTION IF EXISTS lms.prevent_log_auditoria_modify()")
