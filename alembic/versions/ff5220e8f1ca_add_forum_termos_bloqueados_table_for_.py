"""add forum_termos_bloqueados table for US-14 moderation

Revision ID: ff5220e8f1ca
Revises: bcbc58716d17
Create Date: 2026-08-13 14:27:39.983153
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ff5220e8f1ca'
down_revision: Union[str, None] = 'bcbc58716d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('forum_termos_bloqueados',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('termo', sa.String(length=100), nullable=False),
    sa.Column('categoria', sa.String(length=50), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('termo'),
    schema='lms'
    )


def downgrade() -> None:
    op.drop_table('forum_termos_bloqueados', schema='lms')
