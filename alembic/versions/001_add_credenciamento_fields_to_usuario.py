"""add credenciamento fields to usuario

Revision ID: 001_add_credenciamento_fields
Revises: 
Create Date: 2024-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_add_credenciamento_fields'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adicionar campos de credenciamento na tabela usuarios
    op.add_column('usuarios', sa.Column('status_credenciamento', sa.String(20), nullable=True, server_default='pendente'), schema='lms')
    op.add_column('usuarios', sa.Column('aprovado_por', postgresql.UUID(as_uuid=True), nullable=True), schema='lms')
    op.add_column('usuarios', sa.Column('data_aprovacao', sa.DateTime(timezone=True), nullable=True), schema='lms')
    
    # Criar tabela solicitacoes_credenciamento
    op.create_table(
        'solicitacoes_credenciamento',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('usuario_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('perfil_solicitado', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pendente'),
        sa.Column('solicitado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('avaliado_por', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('avaliado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('motivo_rejeicao', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['avaliado_por'], ['lms.usuarios.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['usuario_id'], ['lms.usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='lms'
    )
    
    # Criar tabela aprovacoes_hierarquicas
    op.create_table(
        'aprovacoes_hierarquicas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('solicitacao_id', sa.Integer(), nullable=False),
        sa.Column('aprovador_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('nivel_hierarquico', sa.String(50), nullable=False),
        sa.Column('acao', sa.String(20), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['aprovador_id'], ['lms.usuarios.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['solicitacao_id'], ['lms.solicitacoes_credenciamento.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='lms'
    )


def downgrade() -> None:
    # Remover tabelas criadas
    op.drop_table('aprovacoes_hierarquicas', schema='lms')
    op.drop_table('solicitacoes_credenciamento', schema='lms')
    
    # Remover campos da tabela usuarios
    op.drop_column('usuarios', 'data_aprovacao', schema='lms')
    op.drop_column('usuarios', 'aprovado_por', schema='lms')
    op.drop_column('usuarios', 'status_credenciamento', schema='lms')
