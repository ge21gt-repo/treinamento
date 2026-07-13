import uuid
from datetime import datetime

from pydantic import BaseModel


class PacoteScormBase(BaseModel):
    curso_id: int
    titulo: str
    arquivo_url: str


class PacoteScormCreate(PacoteScormBase):
    pass


class PacoteScormRead(PacoteScormBase):
    id: int
    scorm_version: str | None = None
    criado_por: uuid.UUID | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class TrackingScormCreate(BaseModel):
    sco_id: str
    status: str = "nao_iniciado"
    score_raw: float | None = None
    score_max: float | None = None
    score_min: float | None = None
    lesson_status: str | None = None
    progresso_pct: float | None = None
    dados_cmi: dict | None = None


class TrackingScormRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    pacote_id: int
    sco_id: str
    status: str
    score_raw: float | None = None
    score_max: float | None = None
    score_min: float | None = None
    lesson_status: str | None = None
    progresso_pct: float | None = None
    dados_cmi: dict | None = None
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class ScormRelatorioItem(BaseModel):
    usuario_id: uuid.UUID
    sco_id: str
    status: str
    score_raw: float | None = None
    progresso_pct: float | None = None
    lesson_status: str | None = None


class ScormLaunchResponse(BaseModel):
    url: str
    token: str
    sco_id: str
