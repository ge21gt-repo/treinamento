"""forum topico/resposta: atualizado_em + resposta.removida (issues 49/50)

Revision ID: a1c4e8f2d901
Revises: ad9d802fbf09
Create Date: 2026-09-04 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'a1c4e8f2d901'
down_revision: Union[str, None] = 'ad9d802fbf09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'forum_topicos', sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True), schema='lms'
    )
    op.add_column(
        'forum_respostas', sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True), schema='lms'
    )
    op.add_column(
        'forum_respostas',
        sa.Column('removida', sa.Boolean(), nullable=False, server_default=sa.false()),
        schema='lms',
    )


def downgrade() -> None:
    op.drop_column('forum_respostas', 'removida', schema='lms')
    op.drop_column('forum_respostas', 'atualizado_em', schema='lms')
    op.drop_column('forum_topicos', 'atualizado_em', schema='lms')
