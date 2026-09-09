"""conteudos.disponivel + marca os registros do bucket lms-conteudos morto (issue 46)

Revision ID: c7d3e9a1f204
Revises: f3b7a2e9c145
Create Date: 2026-09-08 09:00:00.000000

O bucket `lms-conteudos` (us-east-2) foi descomissionado sem migrar os dados; os
registros de conteudos criados entre 21/07 e 31/07 ainda apontam pra ele e nunca
mais vao abrir (NoSuchBucket). O bucket atual e `ge21gt-treinamento-idesp`
(us-east-1), que essa migration nao toca.

Em vez de apagar os registros orfaos (poderiam ser uteis pra auditoria, e a
decisao de recuperar/remover e de produto, nao de migration), marca-os como
`disponivel = false` para a tela parar de oferecer um link que nunca abre.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'c7d3e9a1f204'
down_revision: Union[str, None] = 'f3b7a2e9c145'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUCKET_MORTO_PREFIXO = 'https://lms-conteudos.s3.us-east-2.amazonaws.com/%'


def upgrade() -> None:
    op.add_column(
        'conteudos',
        sa.Column('disponivel', sa.Boolean(), nullable=False, server_default=sa.true()),
        schema='lms',
    )
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE lms.conteudos SET disponivel = false WHERE url_arquivo LIKE :prefixo"),
        {"prefixo": BUCKET_MORTO_PREFIXO},
    )


def downgrade() -> None:
    op.drop_column('conteudos', 'disponivel', schema='lms')
