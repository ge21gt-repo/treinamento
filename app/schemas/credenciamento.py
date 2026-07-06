import uuid
from datetime import datetime

from pydantic import BaseModel, Field


__all__ = [
    "SolicitacaoCredenciamentoBase", "SolicitacaoCredenciamentoCreate",
    "SolicitacaoCredenciamentoUpdate", "SolicitacaoCredenciamentoRead",
    "AprovacaoHierarquicaBase", "AprovacaoHierarquicaCreate", "AprovacaoHierarquicaRead",
    "AprovacaoSolicitacaoRequest", "AprovacaoSolicitacaoResponse"
]


class SolicitacaoCredenciamentoBase(BaseModel):
    """Campos base para solicitação de credenciamento"""
    perfil_solicitado: str = Field(..., description="Perfil solicitado (admin_geral, instrutor, gestor, participante)")
    motivo_solicitacao: str | None = Field(None, description="Motivo da solicitação")


class SolicitacaoCredenciamentoCreate(SolicitacaoCredenciamentoBase):
    """Schema para criação de solicitação de credenciamento"""
    usuario_id: uuid.UUID


class SolicitacaoCredenciamentoUpdate(BaseModel):
    """Schema para atualização de solicitação de credenciamento"""
    status: str = Field(..., description="Status da solicitação (pendente, aprovado, rejeitado)")
    observacao_aprovacao: str | None = Field(None, description="Observação sobre a aprovação/rejeição")


class SolicitacaoCredenciamentoRead(SolicitacaoCredenciamentoBase):
    """Schema para leitura de solicitação de credenciamento"""
    id: int
    usuario_id: uuid.UUID
    status: str
    solicitado_em: datetime
    avaliado_por: uuid.UUID | None
    avaliado_em: datetime | None
    motivo_rejeicao: str | None

    model_config = {"from_attributes": True}


class AprovacaoHierarquicaBase(BaseModel):
    """Campos base para aprovação hierárquica"""
    nivel_hierarquico: str = Field(..., description="Nível hierárquico do aprovador (admin_geral, instrutor, gestor)")
    acao: str = Field(..., description="Ação realizada (aprovar, rejeitar)")
    motivo: str | None = Field(None, description="Motivo da decisão")


class AprovacaoHierarquicaCreate(AprovacaoHierarquicaBase):
    """Schema para criação de aprovação hierárquica"""
    solicitacao_id: int
    aprovador_id: uuid.UUID


class AprovacaoHierarquicaRead(AprovacaoHierarquicaBase):
    """Schema para leitura de aprovação hierárquica"""
    id: int
    solicitacao_id: int
    aprovador_id: uuid.UUID
    criado_em: datetime

    model_config = {"from_attributes": True}


class AprovacaoSolicitacaoRequest(BaseModel):
    """Schema para requisição de aprovação/rejeição"""
    observacao: str | None = Field(None, description="Observação sobre a decisão")


class AprovacaoSolicitacaoResponse(BaseModel):
    """Schema para resposta de aprovação/rejeição"""
    message: str
    solicitacao_id: int
    usuario_id: uuid.UUID
    status: str
    perfil_atribuido: str | None = None
    aprovado_por: uuid.UUID | None = None
    data_aprovacao: datetime | None = None
