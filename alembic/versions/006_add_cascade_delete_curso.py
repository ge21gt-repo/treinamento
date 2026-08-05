"""Add ON DELETE CASCADE to progress, enrollment and trail-enrollment FKs

Revision ID: 006
Revises: 005_add_telefone_unique_constraint
Create Date: 2026-07-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006_add_cascade_delete_curso"
down_revision: Union[str, None] = "005_add_telefone_unique_constraint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("progresso_unidade_unidade_id_fkey", "progresso_unidade", type_="foreignkey", schema="lms")
    op.create_foreign_key(
        "progresso_unidade_unidade_id_fkey",
        "progresso_unidade",
        "unidades",
        ["unidade_id"],
        ["id"],
        ondelete="CASCADE",
        source_schema="lms",
        referent_schema="lms",
    )

    op.drop_constraint("inscricoes_curso_id_fkey", "inscricoes", type_="foreignkey", schema="lms")
    op.create_foreign_key(
        "inscricoes_curso_id_fkey",
        "inscricoes",
        "cursos",
        ["curso_id"],
        ["id"],
        ondelete="CASCADE",
        source_schema="lms",
        referent_schema="lms",
    )

    op.drop_constraint("inscricoes_trilha_trilha_id_fkey", "inscricoes_trilha", type_="foreignkey", schema="lms")
    op.create_foreign_key(
        "inscricoes_trilha_trilha_id_fkey",
        "inscricoes_trilha",
        "trilhas_aprendizagem",
        ["trilha_id"],
        ["id"],
        ondelete="CASCADE",
        source_schema="lms",
        referent_schema="lms",
    )


def downgrade() -> None:
    op.drop_constraint("inscricoes_trilha_trilha_id_fkey", "inscricoes_trilha", type_="foreignkey", schema="lms")
    op.create_foreign_key(
        "inscricoes_trilha_trilha_id_fkey",
        "inscricoes_trilha",
        "trilhas_aprendizagem",
        ["trilha_id"],
        ["id"],
        source_schema="lms",
        referent_schema="lms",
    )

    op.drop_constraint("inscricoes_curso_id_fkey", "inscricoes", type_="foreignkey", schema="lms")
    op.create_foreign_key(
        "inscricoes_curso_id_fkey",
        "inscricoes",
        "cursos",
        ["curso_id"],
        ["id"],
        source_schema="lms",
        referent_schema="lms",
    )

    op.drop_constraint("progresso_unidade_unidade_id_fkey", "progresso_unidade", type_="foreignkey", schema="lms")
    op.create_foreign_key(
        "progresso_unidade_unidade_id_fkey",
        "progresso_unidade",
        "unidades",
        ["unidade_id"],
        ["id"],
        source_schema="lms",
        referent_schema="lms",
    )
