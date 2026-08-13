"""add silenciado_ate to usuarios for chat moderation

Revision ID: bcbc58716d17
Revises: b98e1d3fd3ed
Create Date: 2026-08-13 09:46:52.612016
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bcbc58716d17'
down_revision: Union[str, None] = 'b98e1d3fd3ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('silenciado_ate', sa.DateTime(timezone=True), nullable=True), schema='lms')


def downgrade() -> None:
    op.drop_column('usuarios', 'silenciado_ate', schema='lms')
