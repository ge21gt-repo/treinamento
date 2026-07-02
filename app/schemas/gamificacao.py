import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


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


class MissaoRead(MissaoBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


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
