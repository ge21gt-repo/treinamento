import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class AvaliacaoBase(BaseModel):
    unidade_id: int | None = None
    titulo: str
    descricao: str | None = None
    tipo: str
    nota_minima: Decimal = Decimal("60.00")
    tentativas_max: int = 3
    tempo_limite_min: int | None = None
    peso: Decimal = Decimal("1.00")
    ativa: bool = True


class AvaliacaoCreate(AvaliacaoBase):
    pass


class AvaliacaoUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    tipo: str | None = None
    nota_minima: Decimal | None = None
    tentativas_max: int | None = None
    tempo_limite_min: int | None = None
    peso: Decimal | None = None
    ativa: bool | None = None


class AvaliacaoRead(AvaliacaoBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class QuestaoBase(BaseModel):
    avaliacao_id: int
    enunciado: str
    tipo: str
    pontuacao: Decimal = Decimal("1.00")
    ordem: int = 0
    explicacao: str | None = None


class QuestaoCreate(QuestaoBase):
    pass


class QuestaoUpdate(BaseModel):
    enunciado: str | None = None
    tipo: str | None = None
    pontuacao: Decimal | None = None
    ordem: int | None = None
    explicacao: str | None = None


class QuestaoRead(QuestaoBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class AlternativaBase(BaseModel):
    questao_id: int
    texto: str
    correta: bool = False
    ordem: int = 0


class AlternativaCreate(AlternativaBase):
    pass


class AlternativaRead(AlternativaBase):
    id: int

    model_config = {"from_attributes": True}


class RespostaParticipanteBase(BaseModel):
    usuario_id: uuid.UUID
    questao_id: int
    alternativa_id: int | None = None
    resposta_texto: str | None = None
    tentativa_num: int = 1


class RespostaParticipanteCreate(RespostaParticipanteBase):
    pass


class RespostaParticipanteRead(RespostaParticipanteBase):
    id: int
    correta: bool | None = None
    respondido_em: datetime

    model_config = {"from_attributes": True}


class ResultadoAvaliacaoBase(BaseModel):
    usuario_id: uuid.UUID
    avaliacao_id: int
    nota: Decimal
    aprovado: bool
    tentativa_num: int = 1
    tempo_gasto_seg: int | None = None


class ResultadoAvaliacaoCreate(ResultadoAvaliacaoBase):
    pass


class ResultadoAvaliacaoRead(ResultadoAvaliacaoBase):
    id: int
    realizado_em: datetime

    model_config = {"from_attributes": True}
