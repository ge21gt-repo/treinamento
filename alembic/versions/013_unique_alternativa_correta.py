"""unique partial index: exatamente uma alternativa correta por questao

Revision ID: 013
Revises: 012
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_alternativa_correta_por_questao",
        "alternativas",
        ["questao_id"],
        unique=True,
        postgresql_where="correta",
        schema="lms",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_alternativa_correta_por_questao",
        table_name="alternativas",
        postgresql_where="correta",
        schema="lms",
    )
