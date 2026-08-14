"""add unique constraint on inscricoes (curso_id, usuario_id)

Revision ID: 012
Revises: 008
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_inscricoes_curso_usuario", "inscricoes", ["curso_id", "usuario_id"], schema="lms"
    )


def downgrade() -> None:
    op.drop_constraint("uq_inscricoes_curso_usuario", "inscricoes", schema="lms")
