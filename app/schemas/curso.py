import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class TrilhaBase(BaseModel):
    titulo: str
    descricao: str | None = None
    imagem_capa_url: str | None = None
    nivel: str = "iniciante"
    carga_horaria_total: int | None = None
    publicada: bool = False


class TrilhaCreate(TrilhaBase):
    pass


class TrilhaUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    imagem_capa_url: str | None = None
    nivel: str | None = None
    carga_horaria_total: int | None = None
    publicada: bool | None = None


class TrilhaRead(TrilhaBase):
    id: int
    criado_por: uuid.UUID | None = None
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class CursoBase(BaseModel):
    trilha_id: int | None = None
    titulo: str
    descricao: str | None = None
    imagem_capa_url: str | None = None
    ordem: int = 0
    carga_horaria: int | None = None
    pre_requisito_curso_id: int | None = None
    publicado: bool = False
    instrutor_id: uuid.UUID | None = None


class CursoCreate(CursoBase):
    pass


class CursoUpdate(BaseModel):
    trilha_id: int | None = None
    titulo: str | None = None
    descricao: str | None = None
    imagem_capa_url: str | None = None
    ordem: int | None = None
    carga_horaria: int | None = None
    publicado: bool | None = None
    instrutor_id: uuid.UUID | None = None


class CursoRead(CursoBase):
    id: int
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class ModuloBase(BaseModel):
    curso_id: int
    titulo: str
    descricao: str | None = None
    ordem: int = 0


class ModuloCreate(ModuloBase):
    pass


class ModuloUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    ordem: int | None = None


class ModuloRead(ModuloBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class UnidadeBase(BaseModel):
    modulo_id: int
    titulo: str
    tipo: str
    ordem: int = 0
    duracao_estimada: int | None = None


class UnidadeCreate(UnidadeBase):
    pass


class UnidadeUpdate(BaseModel):
    titulo: str | None = None
    tipo: str | None = None
    ordem: int | None = None
    duracao_estimada: int | None = None


class UnidadeRead(UnidadeBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class InscricaoBase(BaseModel):
    usuario_id: uuid.UUID
    curso_id: int


class InscricaoCreate(InscricaoBase):
    pass


class InscricaoRead(InscricaoBase):
    id: int
    status: str
    progresso_pct: Decimal
    data_inscricao: datetime
    data_conclusao: datetime | None = None
    nota_final: Decimal | None = None

    model_config = {"from_attributes": True}


class ProgressoUnidadeBase(BaseModel):
    usuario_id: uuid.UUID
    unidade_id: int


class ProgressoUnidadeCreate(ProgressoUnidadeBase):
    pass


class ProgressoUnidadeUpdate(BaseModel):
    status: str | None = None
    tempo_gasto: int | None = None


class ProgressoUnidadeRead(ProgressoUnidadeBase):
    id: int
    status: str
    tempo_gasto: int
    concluido_em: datetime | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}
