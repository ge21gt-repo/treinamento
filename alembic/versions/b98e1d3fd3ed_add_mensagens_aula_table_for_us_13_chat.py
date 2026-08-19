"""add mensagens_aula table for US-13 chat

Revision ID: b98e1d3fd3ed
Revises: 013
Create Date: 2026-08-13 09:18:21.334637
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b98e1d3fd3ed'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('mensagens_aula',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('aula_id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=False),
    sa.Column('texto', sa.String(length=2000), nullable=False),
    sa.Column('excluida', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['aula_id'], ['lms.aulas_sincronas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['lms.usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='lms'
    )


def downgrade() -> None:
    op.drop_table('mensagens_aula', schema='lms')
