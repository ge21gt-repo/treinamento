"""Add manual-correction fields to respostas_participante and drop unused avaliacoes.peso

Revision ID: 007
Revises: 006_add_cascade_delete_curso
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006_add_cascade_delete_curso"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("respostas_participante", sa.Column("pontuacao_atribuida", sa.Numeric(5, 2), nullable=True), schema="lms")
    op.add_column("respostas_participante", sa.Column("corrigida_por", sa.UUID(as_uuid=True), nullable=True), schema="lms")
    op.add_column("respostas_participante", sa.Column("corrigida_em", sa.DateTime(timezone=True), nullable=True), schema="lms")
    op.create_foreign_key(
        "respostas_participante_corrigida_por_fkey",
        "respostas_participante",
        "usuarios",
        ["corrigida_por"],
        ["id"],
        source_schema="lms",
        referent_schema="lms",
    )

    op.drop_column("avaliacoes", "peso", schema="lms")


def downgrade() -> None:
    op.add_column("avaliacoes", sa.Column("peso", sa.Numeric(3, 2), nullable=True), schema="lms")
    op.drop_constraint("respostas_participante_corrigida_por_fkey", "respostas_participante", type_="foreignkey", schema="lms")
    op.drop_column("respostas_participante", "corrigida_em", schema="lms")
    op.drop_column("respostas_participante", "corrigida_por", schema="lms")
    op.drop_column("respostas_participante", "pontuacao_atribuida", schema="lms")
