"""usuarios: versao do termo aceito e IP do aceite (issue 95 / #119)

Quem entrava pelo Keycloak nascia com aceite_lgpd=True, isto e, a plataforma
registrava um consentimento que a pessoa nunca deu, e nao havia rota para
aceitar depois.

As duas colunas sao anulaveis, e o `versao_termo_lgpd` nulo das linhas
existentes e exatamente o mecanismo do re-aceite decidido em produto: nulo
nunca casa com a versao em vigor (VERSAO_TERMO_LGPD), entao todo mundo que ja
existe aparece como pendente e aceita de novo no primeiro acesso.

De proposito a migration NAO mexe em aceite_lgpd nem em data_aceite_lgpd das
linhas antigas: apagar essas colunas destruiria a informacao de que a pessoa
aceitou, e quando. O re-aceite nao precisa disso.

Revision ID: d3f6a82c5e19
Revises: a7e4c91b2d58
Create Date: 2026-10-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'd3f6a82c5e19'
down_revision: Union[str, None] = 'a7e4c91b2d58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column("versao_termo_lgpd", sa.String(length=20), nullable=True),
        schema="lms",
    )
    op.add_column(
        "usuarios",
        sa.Column("ip_aceite_lgpd", postgresql.INET(), nullable=True),
        schema="lms",
    )


def downgrade() -> None:
    op.drop_column("usuarios", "ip_aceite_lgpd", schema="lms")
    op.drop_column("usuarios", "versao_termo_lgpd", schema="lms")
