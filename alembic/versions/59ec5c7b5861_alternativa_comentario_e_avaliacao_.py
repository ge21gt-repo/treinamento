"""alternativa comentario e avaliacao mostrar_gabarito (issue 90)

Revision ID: 59ec5c7b5861
Revises: df7bdabfe046
Create Date: 2026-10-06 14:51:12.147175
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '59ec5c7b5861'
down_revision: Union[str, None] = 'df7bdabfe046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alternativas",
        sa.Column("comentario", sa.Text(), nullable=True),
        schema="lms",
    )
    op.add_column(
        "avaliacoes",
        sa.Column("mostrar_gabarito", sa.String(length=30), server_default="sempre", nullable=False),
        schema="lms",
    )


def downgrade() -> None:
    op.drop_column("avaliacoes", "mostrar_gabarito", schema="lms")
    op.drop_column("alternativas", "comentario", schema="lms")
