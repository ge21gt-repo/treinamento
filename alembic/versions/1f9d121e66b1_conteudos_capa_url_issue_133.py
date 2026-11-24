"""conteudos capa_url (issue 133)

Revision ID: 1f9d121e66b1
Revises: e5a913d7b204
Create Date: 2026-11-24 15:01:34.480429
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1f9d121e66b1'
down_revision: Union[str, None] = 'e5a913d7b204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conteudos",
        sa.Column("capa_url", sa.Text(), nullable=True),
        schema="lms",
    )


def downgrade() -> None:
    op.drop_column("conteudos", "capa_url", schema="lms")
