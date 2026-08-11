"""add codigo_acesso and data_hora_fim to aulas_sincronas

Revision ID: 008
Revises: 007
Create Date: 2026-08-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "aulas_sincronas",
        sa.Column("codigo_acesso", sa.String(20), nullable=True),
        schema="lms",
    )
    op.add_column(
        "aulas_sincronas",
        sa.Column("data_hora_fim", sa.DateTime(timezone=True), nullable=True),
        schema="lms",
    )
    op.create_index("ix_aulas_sincronas_codigo_acesso", "aulas_sincronas", ["codigo_acesso"], schema="lms")

    op.create_table(
        "presenca_aula",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("aula_id", sa.Integer(), sa.ForeignKey("lms.aulas_sincronas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms.usuarios.id"), nullable=False),
        sa.Column("hora_entrada", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hora_saida", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tempo_permanencia_seg", sa.Integer(), nullable=True),
        sa.Column("presente", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("ip_acesso", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="lms",
    )
    op.create_index("ix_presenca_aula_aula_id", "presenca_aula", ["aula_id"], schema="lms")


def downgrade() -> None:
    op.drop_index("ix_presenca_aula_aula_id", table_name="presenca_aula", schema="lms")
    op.drop_table("presenca_aula", schema="lms")
    op.drop_index("ix_aulas_sincronas_codigo_acesso", table_name="aulas_sincronas", schema="lms")
    op.drop_column("aulas_sincronas", "data_hora_fim", schema="lms")
    op.drop_column("aulas_sincronas", "codigo_acesso", schema="lms")
