"""log_auditoria: user_agent e dispositivo (issue 96 / #120)

A aba de Alteracoes dos Logs nao mostrava Dispositivo nem Navegador porque as
colunas nao existiam em log_auditoria - so em log_acesso. As duas sao anulaveis:
as linhas antigas ficam null e a tela mostra um traco.

user_agent e Text, como em log_acesso.user_agent, e nao varchar(1000): um
user-agent acima do limite faria o INSERT da auditoria estourar, e a auditoria
nao pode derrubar a operacao que ela registra.

Revision ID: c4b8e2f1a930
Revises: 59ec5c7b5861
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'c4b8e2f1a930'
down_revision: Union[str, None] = '59ec5c7b5861'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "log_auditoria",
        sa.Column("user_agent", sa.Text(), nullable=True),
        schema="lms",
    )
    op.add_column(
        "log_auditoria",
        sa.Column("dispositivo", sa.String(length=20), nullable=True),
        schema="lms",
    )


def downgrade() -> None:
    op.drop_column("log_auditoria", "dispositivo", schema="lms")
    op.drop_column("log_auditoria", "user_agent", schema="lms")
