"""add tokens_reset_senha

Revision ID: 002_add_tokens_reset_senha
Revises: 001_add_credenciamento_fields
Create Date: 2024-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_add_tokens_reset_senha'
down_revision: Union[str, None] = '001_add_credenciamento_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tokens_reset_senha',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('usuario_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('lms.usuarios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('utilizado', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        schema='lms',
    )


def downgrade() -> None:
    op.drop_table('tokens_reset_senha', schema='lms')
