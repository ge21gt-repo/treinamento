"""add aulas_sincronas, mensagens_curso cols to unidades

Revision ID: 003_add_aulas_chat_unidades
Revises: 002_add_tokens_reset_senha
Create Date: 2024-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003_add_aulas_chat_unidades'
down_revision: Union[str, None] = '002_add_tokens_reset_senha'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('unidades', sa.Column('conteudo_url', sa.Text(), nullable=True), schema='lms')
    op.add_column('unidades', sa.Column('url_externa', sa.Text(), nullable=True), schema='lms')

    op.create_table(
        'aulas_sincronas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('curso_id', sa.Integer(), sa.ForeignKey('lms.cursos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('titulo', sa.String(200), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('data_hora', sa.DateTime(timezone=True), nullable=False),
        sa.Column('link_externo', sa.Text(), nullable=True),
        sa.Column('duracao_minutos', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), server_default='agendada', nullable=False),
        sa.Column('criado_por', postgresql.UUID(as_uuid=True), sa.ForeignKey('lms.usuarios.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='lms',
    )

    op.create_table(
        'mensagens_curso',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('curso_id', sa.Integer(), sa.ForeignKey('lms.cursos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('usuario_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('lms.usuarios.id'), nullable=False),
        sa.Column('texto', sa.String(2000), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='lms',
    )


def downgrade() -> None:
    op.drop_table('mensagens_curso', schema='lms')
    op.drop_table('aulas_sincronas', schema='lms')
    op.drop_column('unidades', 'url_externa', schema='lms')
    op.drop_column('unidades', 'conteudo_url', schema='lms')
