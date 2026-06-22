import uuid
from datetime import datetime

from pydantic import BaseModel


class SessaoAoVivoBase(BaseModel):
    curso_id: int | None = None
    titulo: str
    descricao: str | None = None
    instrutor_id: uuid.UUID
    data_hora_inicio: datetime
    data_hora_fim: datetime | None = None
    url_transmissao: str | None = None
    codigo_acesso: str | None = None
    max_participantes: int | None = None


class SessaoAoVivoCreate(SessaoAoVivoBase):
    pass


class SessaoAoVivoUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    data_hora_inicio: datetime | None = None
    data_hora_fim: datetime | None = None
    status: str | None = None
    url_transmissao: str | None = None
    url_gravacao: str | None = None
    max_participantes: int | None = None


class SessaoAoVivoRead(SessaoAoVivoBase):
    id: int
    status: str
    url_gravacao: str | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class PresencaBase(BaseModel):
    sessao_id: int
    usuario_id: uuid.UUID
    hora_entrada: datetime


class PresencaCreate(PresencaBase):
    pass


class PresencaUpdate(BaseModel):
    hora_saida: datetime | None = None
    tempo_permanencia_seg: int | None = None
    presente: bool | None = None


class PresencaRead(PresencaBase):
    id: int
    hora_saida: datetime | None = None
    tempo_permanencia_seg: int | None = None
    presente: bool
    ip_acesso: str | None = None

    model_config = {"from_attributes": True}
