"""forum_termos_bloqueados: remove palavras administrativas soltas do seed (issue 51)

Revision ID: f3b7a2e9c145
Revises: a1c4e8f2d901
Create Date: 2026-09-04 12:05:00.000000

O seed antigo bloqueava "presidente", "candidato", "partido", "eleicao"/"eleicoes" e
"governador" como palavras soltas -- vocabulario administrativo comum (ex.: "presidente
da comissao de licitacao") que passou a ser recusado por engano. `seed_termos_default()`
so popula quando a tabela esta vazia, entao trocar a lista no codigo (app/services/
moderacao.py) nao limpa o que ja foi semeado; esta migration remove os termos antigos e
insere as frases que os substituem.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'f3b7a2e9c145'
down_revision: Union[str, None] = 'a1c4e8f2d901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TERMOS_REMOVIDOS = ["eleicao", "eleicoes", "presidente", "prefeito", "governador", "partido", "candidato"]

TERMOS_NOVOS = [
    ("campanha eleitoral", "politico"),
    ("voto em", "politico"),
    ("apoie o candidato", "politico"),
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM lms.forum_termos_bloqueados WHERE termo = ANY(:termos)"),
        {"termos": TERMOS_REMOVIDOS},
    )
    for termo, categoria in TERMOS_NOVOS:
        conn.execute(
            sa.text(
                "INSERT INTO lms.forum_termos_bloqueados (termo, categoria, ativo) "
                "VALUES (:termo, :categoria, true) ON CONFLICT (termo) DO NOTHING"
            ),
            {"termo": termo, "categoria": categoria},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM lms.forum_termos_bloqueados WHERE termo = ANY(:termos)"),
        {"termos": [termo for termo, _ in TERMOS_NOVOS]},
    )
    for termo in TERMOS_REMOVIDOS:
        conn.execute(
            sa.text(
                "INSERT INTO lms.forum_termos_bloqueados (termo, categoria, ativo) "
                "VALUES (:termo, 'politico', true) ON CONFLICT (termo) DO NOTHING"
            ),
            {"termo": termo},
        )
