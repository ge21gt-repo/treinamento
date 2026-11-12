"""Schemas dos eventos e do resumo dos tours de ajuda (issue #125)."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

# A lista fechada da issue. Validar aqui, e nao no banco, mantem o 422 com
# mensagem legivel em vez de um erro de constraint.
EVENTOS = (
    "convite_exibido",
    "convite_adiado",
    "convite_dispensado",
    "tour_iniciado",
    "passo_visto",
    "tour_concluido",
    "tour_fechado",
    "tour_util",
)

# Os seis perfis semeados no boot. Repetidos aqui de proposito, e nao lidos do
# PERFIL_PERMISSOES: o papel do evento e o papel da INTERFACE em que a pessoa
# estava, nao a permissao dela - se um perfil novo aparecer sem tour, a lista
# nao deve crescer sozinha.
PAPEIS = (
    "administrador_geral",
    "administrador",
    "instrutor",
    "auditor",
    "gestor",
    "participante",
)

EVENTOS_COM_PASSO = ("passo_visto", "tour_fechado")
EVENTOS_COM_UTIL = ("tour_util",)

LOTE_MAXIMO = 50
_TOUR_ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")


class TourEventoIn(BaseModel):
    tour_id: str
    papel: str
    evento: str
    passo: int | None = None
    util: bool | None = None

    model_config = {"extra": "forbid"}

    @field_validator("tour_id")
    @classmethod
    def _tour_id_valido(cls, v: str) -> str:
        if not _TOUR_ID_RE.match(v or ""):
            raise ValueError("tour_id deve ter de 1 a 64 caracteres, em minusculas, numeros e hifen")
        return v

    @field_validator("papel")
    @classmethod
    def _papel_valido(cls, v: str) -> str:
        if v not in PAPEIS:
            raise ValueError(f"papel desconhecido: {v}")
        return v

    @field_validator("evento")
    @classmethod
    def _evento_valido(cls, v: str) -> str:
        if v not in EVENTOS:
            raise ValueError(f"evento desconhecido: {v}")
        return v

    @model_validator(mode="after")
    def _passo_e_util_so_onde_cabem(self):
        """`passo` so em passo_visto/tour_fechado e `util` so em tour_util.

        Recusar em vez de ignorar: um campo no lugar errado e sinal de cliente
        com defeito, e aceitar em silencio deixaria a contagem torta sem
        ninguem perceber.
        """
        if self.passo is not None and self.evento not in EVENTOS_COM_PASSO:
            raise ValueError(f"passo nao se aplica ao evento {self.evento}")
        if self.passo is not None and self.passo < 0:
            raise ValueError("passo nao pode ser negativo")
        if self.util is not None and self.evento not in EVENTOS_COM_UTIL:
            raise ValueError(f"util nao se aplica ao evento {self.evento}")
        return self


class TourEventosLote(BaseModel):
    # Lista vazia passa e nao grava nada: o front esvazia a fila ao sair da
    # pagina, e uma fila vazia nao e erro dele.
    eventos: list[TourEventoIn] = Field(default_factory=list, max_length=LOTE_MAXIMO)

    model_config = {"extra": "forbid"}


class TourResumoItem(BaseModel):
    """Contagens de um tour, ou de um papel dentro dele."""

    convites_exibidos: int = 0
    adiados: int = 0
    dispensados: int = 0
    iniciados: int = 0
    concluidos: int = 0
    fechados_por_passo: dict[str, int] = Field(default_factory=dict)
    util_sim: int = 0
    util_nao: int = 0


class TourResumoTour(TourResumoItem):
    tour_id: str
    # O mesmo total, quebrado por papel, como a issue pede.
    por_papel: dict[str, TourResumoItem] = Field(default_factory=dict)


class TourResumoRead(BaseModel):
    de: datetime | None = None
    ate: datetime | None = None
    tours: list[TourResumoTour] = Field(default_factory=list)
