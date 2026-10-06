"""unidade conteudo_texto e formato_texto (issue 91)

Revision ID: df7bdabfe046
Revises: 179fc9c3ac09
Create Date: 2026-10-06 14:49:57.401277
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'df7bdabfe046'
down_revision: Union[str, None] = '179fc9c3ac09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "unidades",
        sa.Column("conteudo_texto", sa.Text(), nullable=True),
        schema="lms",
    )
    op.add_column(
        "unidades",
        sa.Column("formato_texto", sa.String(length=10), server_default="texto", nullable=False),
        schema="lms",
    )


def downgrade() -> None:
    op.drop_column("unidades", "formato_texto", schema="lms")
    op.drop_column("unidades", "conteudo_texto", schema="lms")
