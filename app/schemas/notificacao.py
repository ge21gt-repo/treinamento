"""Schemas de notificacoes (issue 28)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificacaoRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    tipo: str
    titulo: str
    corpo: str | None = None
    referencia_tipo: str | None = None
    referencia_id: int | None = None
    lida: bool
    criado_em: datetime
    lida_em: datetime | None = None

    model_config = {"from_attributes": True}


class NotificacoesListaRead(BaseModel):
    itens: list[NotificacaoRead]
    total: int
    nao_lidas: int