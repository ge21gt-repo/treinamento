import uuid
from datetime import datetime

from pydantic import BaseModel


class SandboxIniciarRequest(BaseModel):
    observacao: str | None = None


class SandboxSessaoRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    status: str
    observacao: str | None = None
    iniciado_em: datetime
    encerrado_em: datetime | None = None

    model_config = {"from_attributes": True}


class SandboxEncerrarResponse(BaseModel):
    message: str
    sessao_id: int
    usuario_id: uuid.UUID
    duracao_segundos: int | None = None
