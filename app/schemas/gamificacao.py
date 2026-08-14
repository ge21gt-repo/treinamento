import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator


TIPOS_MISSAO = frozenset({"diaria", "semanal", "especial"})


class NivelBase(BaseModel):
    nome: str
    xp_minimo: int
    icone_url: str | None = None
    ordem: int


class NivelCreate(NivelBase):
    pass


class NivelRead(NivelBase):
    id: int

    model_config = {"from_attributes": True}


class PontosXPBase(BaseModel):
    usuario_id: uuid.UUID
    quantidade: int
    origem: str
    referencia_id: int | None = None
    descricao: str | None = None


class PontosXPCreate(PontosXPBase):
    pass


class PontosXPRead(PontosXPBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class BadgeBase(BaseModel):
    nome: str
    descricao: str | None = None
    icone_url: str | None = None
    criterio_tipo: str
    criterio_valor: int
    ativo: bool = True


class BadgeCreate(BadgeBase):
    pass


class BadgeRead(BadgeBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class UsuarioBadgeCreate(BaseModel):
    usuario_id: uuid.UUID
    badge_id: int


class UsuarioBadgeRead(BaseModel):
    usuario_id: uuid.UUID
    badge_id: int
    conquistado_em: datetime

    model_config = {"from_attributes": True}


class MissaoBase(BaseModel):
    titulo: str
    descricao: str | None = None
    tipo: str
    xp_recompensa: int
    criterio: dict
    data_inicio: date | None = None
    data_fim: date | None = None
    ativa: bool = True

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        if v not in TIPOS_MISSAO:
            raise ValueError(f"tipo deve ser um de: {', '.join(sorted(TIPOS_MISSAO))}")
        return v


class MissaoCreate(MissaoBase):
    pass


class MissaoUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    tipo: str | None = None
    xp_recompensa: int | None = None
    criterio: dict | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    ativa: bool | None = None

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v: str | None) -> str | None:
        if v is not None and v not in TIPOS_MISSAO:
            raise ValueError(f"tipo deve ser um de: {', '.join(sorted(TIPOS_MISSAO))}")
        return v


class MissaoRead(MissaoBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class MissaoComProgressoRead(MissaoRead):
    usuario_status: str | None = None
    usuario_progresso_pct: Decimal | None = None
    usuario_concluido_em: datetime | None = None


class UsuarioMissaoCreate(BaseModel):
    usuario_id: uuid.UUID
    missao_id: int


class UsuarioMissaoUpdate(BaseModel):
    status: str | None = None
    progresso_pct: Decimal | None = None


class UsuarioMissaoRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    missao_id: int
    status: str
    progresso_pct: Decimal
    concluido_em: datetime | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class StreakRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    dias_consecutivos: int
    maior_streak: int
    ultimo_acesso_dia: date | None = None
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    usuario_id: uuid.UUID
    nome_completo: str
    xp_total: int
    nivel: str


class NivelInfo(BaseModel):
    nome: str
    ordem: int
    xp_minimo: int
    icone_url: str | None = None


class ProximoNivelInfo(BaseModel):
    nome: str
    ordem: int
    xp_minimo: int
    xp_restante: int
    progresso_pct: float


class BadgePerfilRead(BaseModel):
    id: int
    nome: str
    descricao: str | None = None
    icone_url: str | None = None
    conquistado_em: datetime


class HistoricoXPRead(BaseModel):
    quantidade: int
    origem: str
    descricao: str | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class StreakPerfilRead(BaseModel):
    dias_consecutivos: int
    maior_streak: int


class PerfilGamificadoRead(BaseModel):
    usuario_id: uuid.UUID
    nome_completo: str
    xp_total: int
    nivel_atual: NivelInfo
    proximo_nivel: ProximoNivelInfo | None = None
    badges: list[BadgePerfilRead]
    streak: StreakPerfilRead
    historico_recente: list[HistoricoXPRead]


class BadgeUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    icone_url: str | None = None
    criterio_tipo: str | None = None
    criterio_valor: int | None = None
    ativo: bool | None = None


class BadgeProgressoRead(BaseModel):
    badge_id: int
    nome: str
    descricao: str | None = None
    icone_url: str | None = None
    criterio_tipo: str
    criterio_valor: int
    progresso_atual: int
    conquistada: bool
