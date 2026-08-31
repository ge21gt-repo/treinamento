"""tabela notificacoes (issue 28)

Revision ID: 1a7af45bb737
Revises: 42b0690901d1
Create Date: 2026-08-27 07:54:25.322999
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1a7af45bb737'
down_revision: Union[str, None] = '42b0690901d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=True),
        sa.Column("referencia_tipo", sa.String(50), nullable=True),
        sa.Column("referencia_id", sa.Integer(), nullable=True),
        sa.Column("lida", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("lida_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["lms.usuarios.id"]),
        schema="lms",
    )
    op.create_index("ix_notificacoes_usuario_id", "notificacoes", ["usuario_id"], schema="lms")


def downgrade() -> None:
    op.drop_index("ix_notificacoes_usuario_id", table_name="notificacoes", schema="lms")
    op.drop_table("notificacoes", schema="lms")
