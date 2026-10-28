"""tour_eventos: contagens de uso dos tours de ajuda (issue 101 / #125)

Nada media os tours: nao dava para saber quantas pessoas comecam, quantas
terminam, em que passo saem, quantas dispensam e se acharam util.

A decisao de produto registrada na issue e guardar SO contagens. Por isso a
tabela NAO tem usuario_id, nem ip_address, nem user_agent - de proposito, para
a medicao nao exigir mudanca na Politica de Privacidade. O preco aceito e nao
dar para contar pessoas distintas.

`passo` e `util` sao anulaveis porque so se aplicam a alguns eventos: `passo`
em passo_visto e tour_fechado, `util` em tour_util. A rota recusa o que vier
fora disso.

O indice em criado_em existe porque o resumo filtra por periodo e a tabela
cresce rapido - o front manda lote de poucos em poucos segundos.

Revision ID: e5a913d7b204
Revises: d3f6a82c5e19
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'e5a913d7b204'
down_revision: Union[str, None] = 'd3f6a82c5e19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tour_eventos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tour_id", sa.String(length=64), nullable=False),
        sa.Column("papel", sa.String(length=32), nullable=False),
        sa.Column("evento", sa.String(length=32), nullable=False),
        sa.Column("passo", sa.Integer(), nullable=True),
        sa.Column("util", sa.Boolean(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="lms",
    )
    op.create_index("ix_tour_eventos_criado_em", "tour_eventos", ["criado_em"], schema="lms")


def downgrade() -> None:
    op.drop_index("ix_tour_eventos_criado_em", table_name="tour_eventos", schema="lms")
    op.drop_table("tour_eventos", schema="lms")
