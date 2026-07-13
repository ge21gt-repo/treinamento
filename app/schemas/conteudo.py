import uuid
from datetime import datetime

from pydantic import BaseModel


class ConteudoBase(BaseModel):
    unidade_id: int | None = None
    tipo_midia: str
    titulo: str
    descricao: str | None = None
    mime_type: str | None = None
    url_arquivo: str
    tamanho_bytes: int | None = None
    duracao_segundos: int | None = None
    ordem: int = 0


class ConteudoCreate(ConteudoBase):
    pass


class ConteudoUpdate(BaseModel):
    tipo_midia: str | None = None
    titulo: str | None = None
    descricao: str | None = None
    url_arquivo: str | None = None
    tamanho_bytes: int | None = None
    duracao_segundos: int | None = None
    ordem: int | None = None


class ConteudoRead(ConteudoBase):
    id: int
    criado_por: uuid.UUID | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class MaterialComplementarBase(BaseModel):
    curso_id: int | None = None
    titulo: str
    tipo: str
    url_arquivo: str


class MaterialComplementarCreate(MaterialComplementarBase):
    pass


class MaterialComplementarUpdate(BaseModel):
    titulo: str | None = None
    tipo: str | None = None
    url_arquivo: str | None = None


class MaterialComplementarRead(MaterialComplementarBase):
    id: int
    criado_por: uuid.UUID | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class EntregaAtividadeBase(BaseModel):
    unidade_id: int
    titulo: str
    descricao: str | None = None
    url_arquivo: str
    tamanho_bytes: int | None = None
    mime_type: str | None = None


class EntregaAtividadeCreate(EntregaAtividadeBase):
    pass


class EntregaAtividadeRead(EntregaAtividadeBase):
    id: int
    usuario_id: uuid.UUID
    status: str
    nota: float | None = None
    feedback: str | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class EntregaAtividadeCorrigir(BaseModel):
    nota: float
    feedback: str
