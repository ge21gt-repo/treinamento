"""unique constraint usuario_missao (issue 22)

Revision ID: de126b1182f8
Revises: ff5220e8f1ca
Create Date: 2026-08-19 14:57:04.516968
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'de126b1182f8'
down_revision: Union[str, None] = 'ff5220e8f1ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_usuario_missao",
        "usuario_missao",
        ["usuario_id", "missao_id"],
        schema="lms",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_usuario_missao",
        "usuario_missao",
        schema="lms",
    )
