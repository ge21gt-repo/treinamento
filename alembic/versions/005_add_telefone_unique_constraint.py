"""Add unique constraint on usuarios.telefone

Revision ID: 005
Revises: 004_add_conteudo_materiais_entregas_scorm_teams
Create Date: 2026-07-14
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "005_add_telefone_unique_constraint"
down_revision: Union[str, None] = "004_add_conteudo_materiais_entregas_scorm_teams"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("usuarios_telefone_key", "usuarios", ["telefone"], schema="lms")


def downgrade() -> None:
    op.drop_constraint("usuarios_telefone_key", "usuarios", type_="unique", schema="lms")
