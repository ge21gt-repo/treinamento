"""usuario_preferencias: preferencias de interface por usuario (issue 100 / #124)

Os tours de ajuda e as preferencias de interface (menuRecolhido, papelInicial)
viviam so no localStorage: quem trocava de navegador ou de maquina via os tours
de novo. Nao havia tabela nem rota de preferencia.

JSONB sem esquema fixo, de proposito: o front e dono do significado das chaves,
e cada tour novo exigiria uma migration se houvesse coluna por preferencia.

usuario_id e a chave primaria (uma linha por pessoa) e o ON DELETE CASCADE leva
as preferencias junto quando o usuario e removido.

Revision ID: a7e4c91b2d58
Revises: c4b8e2f1a930
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'a7e4c91b2d58'
down_revision: Union[str, None] = 'c4b8e2f1a930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuario_preferencias",
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "dados",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["lms.usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id"),
        schema="lms",
    )


def downgrade() -> None:
    op.drop_table("usuario_preferencias", schema="lms")
