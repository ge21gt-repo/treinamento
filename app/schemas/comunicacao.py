import uuid
from datetime import datetime

from pydantic import BaseModel


class MensagemChatBase(BaseModel):
    sessao_id: int | None = None
    conteudo: str
    tipo: str = "texto"


class MensagemChatCreate(MensagemChatBase):
    pass


class MensagemChatRead(MensagemChatBase):
    id: int
    usuario_id: uuid.UUID
    enviado_em: datetime

    model_config = {"from_attributes": True}


class ForumTopicoBase(BaseModel):
    curso_id: int
    titulo: str
    conteudo: str


class ForumTopicoCreate(ForumTopicoBase):
    pass


class ForumTopicoUpdate(BaseModel):
    titulo: str | None = None
    conteudo: str | None = None
    fixado: bool | None = None
    fechado: bool | None = None


class ForumTopicoRead(ForumTopicoBase):
    id: int
    autor_id: uuid.UUID
    fixado: bool
    fechado: bool
    criado_em: datetime

    model_config = {"from_attributes": True}


class ForumRespostaBase(BaseModel):
    topico_id: int
    conteudo: str
    resposta_pai_id: int | None = None


class ForumRespostaCreate(ForumRespostaBase):
    pass


class ForumRespostaRead(ForumRespostaBase):
    id: int
    autor_id: uuid.UUID
    criado_em: datetime

    model_config = {"from_attributes": True}


class ForumTermoBloqueadoCreate(BaseModel):
    termo: str
    categoria: str | None = None


class ForumTermoBloqueadoRead(BaseModel):
    id: int
    termo: str
    categoria: str | None = None
    ativo: bool
    criado_em: datetime

    model_config = {"from_attributes": True}
