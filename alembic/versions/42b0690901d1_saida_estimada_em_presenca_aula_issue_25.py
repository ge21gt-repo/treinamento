"""saida_estimada em presenca_aula (issue 25)

Revision ID: 42b0690901d1
Revises: de126b1182f8
Create Date: 2026-08-26 14:40:45.993539
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '42b0690901d1'
down_revision: Union[str, None] = 'de126b1182f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("presenca_aula", sa.Column("saida_estimada", sa.Boolean(), nullable=False, server_default="false"), schema="lms")


def downgrade() -> None:
    op.drop_column("presenca_aula", "saida_estimada", schema="lms")
