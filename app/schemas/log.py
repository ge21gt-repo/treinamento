import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_serializer
from pydantic.networks import IPvAnyAddress


class LogAcessoRead(BaseModel):
    id: int
    usuario_id: uuid.UUID | None = None
    acao: str
    recurso_tipo: str | None = None
    recurso_id: int | None = None
    ip_address: IPvAnyAddress | None = None
    user_agent: str | None = None
    dispositivo: str | None = None
    criado_em: datetime

    @field_serializer("ip_address")
    def _ip_como_texto(self, valor: IPvAnyAddress | None) -> str | None:
        return str(valor) if valor is not None else None

    model_config = {"from_attributes": True}


class LogAuditoriaRead(BaseModel):
    id: int
    usuario_id: uuid.UUID | None = None
    acao: str
    tabela_afetada: str
    registro_id: str
    dados_anteriores: dict | None = None
    dados_novos: dict | None = None
    ip_address: IPvAnyAddress | None = None
    criado_em: datetime

    @field_serializer("ip_address")
    def _ip_como_texto(self, valor: IPvAnyAddress | None) -> str | None:
        return str(valor) if valor is not None else None

    model_config = {"from_attributes": True}


class MetricaEngajamentoRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    data_referencia: date
    tempo_total_seg: int
    conteudos_acessados: int
    avaliacoes_realizadas: int
    mensagens_enviadas: int
    sessoes_assistidas: int
    xp_ganho: int
    criado_em: datetime

    model_config = {"from_attributes": True}
