"""usuario_aula_silenciado (issue 25 P3)

Revision ID: ad9d802fbf09
Revises: 42b0690901d1
Create Date: 2026-08-31 07:40:37.957960
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ad9d802fbf09'
down_revision: Union[str, None] = '42b0690901d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuario_aula_silenciado",
        sa.Column("usuario_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aula_id", sa.Integer(), nullable=False),
        sa.Column("silenciado_ate", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["usuario_id"], ["lms.usuarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aula_id"], ["lms.aulas_sincronas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id", "aula_id"),
        sa.UniqueConstraint("usuario_id", "aula_id", name="uq_usuario_aula_silenciado"),
        schema="lms",
    )


def downgrade() -> None:
    op.drop_table("usuario_aula_silenciado", schema="lms")
