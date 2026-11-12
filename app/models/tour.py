"""Eventos de uso dos tours de ajuda (issue #125).

A decisao de produto da issue e guardar SO contagens: a linha nao tem
`usuario_id`, nem IP, nem user-agent, de proposito - assim a medicao nao pede
mudanca na Politica de Privacidade. O preco aceito e nao dar para contar
pessoas distintas, apenas eventos.

Por isso esta tabela nao e `log_acesso` nem `log_auditoria`: aquelas registram
acesso e alteracao de dados, ligados a uma pessoa, e esta registra interface,
ligada a ninguem.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TourEvento(Base):
    __tablename__ = "tour_eventos"
    # O resumo filtra por periodo; a tabela cresce rapido, porque o front manda
    # lote a cada poucos segundos. Index explicito, com o nome exato da
    # migration, e nao index=True (que geraria ix_lms_tour_eventos_criado_em e
    # duplicaria o da migration).
    __table_args__ = (Index("ix_tour_eventos_criado_em", "criado_em"), {"schema": "lms"})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tour_id: Mapped[str] = mapped_column(String(64), nullable=False)
    papel: Mapped[str] = mapped_column(String(32), nullable=False)
    evento: Mapped[str] = mapped_column(String(32), nullable=False)
    # Anulaveis porque so fazem sentido em alguns eventos: `passo` em
    # passo_visto e tour_fechado, `util` em tour_util.
    passo: Mapped[int | None] = mapped_column(Integer)
    util: Mapped[bool | None] = mapped_column(Boolean)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
