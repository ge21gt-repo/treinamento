"""add keycloak_sub to usuarios

Revision ID: 21145d4bb9be
Revises: c7d3e9a1f204
Create Date: 2026-09-14 14:57:47.672781
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "21145d4bb9be"
down_revision: Union[str, None] = "c7d3e9a1f204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("keycloak_sub", sa.String(length=255), nullable=True), schema="lms")
    op.create_index(op.f("ix_lms_usuarios_keycloak_sub"), "usuarios", ["keycloak_sub"], unique=True, schema="lms")
    op.add_column(
        "usuarios",
        sa.Column("auth_provider", sa.String(length=20), server_default="local", nullable=False),
        schema="lms",
    )
    op.alter_column("usuarios", "senha_hash", existing_type=sa.VARCHAR(length=255), nullable=True, schema="lms")


def downgrade() -> None:
    op.alter_column("usuarios", "senha_hash", existing_type=sa.VARCHAR(length=255), nullable=False, schema="lms")
    op.drop_column("usuarios", "auth_provider", schema="lms")
    op.drop_index(op.f("ix_lms_usuarios_keycloak_sub"), table_name="usuarios", schema="lms")
    op.drop_column("usuarios", "keycloak_sub", schema="lms")
