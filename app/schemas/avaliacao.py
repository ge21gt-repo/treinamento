import uuid
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, field_serializer, field_validator

TIPOS_QUESTAO = {"multipla_escolha", "verdadeiro_falso", "dissertativa"}


class AvaliacaoBase(BaseModel):
    unidade_id: int | None = None
    titulo: str
    descricao: str | None = None
    tipo: str
    nota_minima: Decimal = Decimal("60.00")
    tentativas_max: int = 3
    tempo_limite_min: int | None = None
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

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        if v not in TIPOS_QUESTAO:
            raise ValueError(f"tipo deve ser um de: {', '.join(sorted(TIPOS_QUESTAO))}")
        return v


class QuestaoCreate(QuestaoBase):
    pass


class QuestaoUpdate(BaseModel):
    enunciado: str | None = None
    tipo: str | None = None
    pontuacao: Decimal | None = None
    ordem: int | None = None
    explicacao: str | None = None

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v: str | None) -> str | None:
        if v is not None and v not in TIPOS_QUESTAO:
            raise ValueError(f"tipo deve ser um de: {', '.join(sorted(TIPOS_QUESTAO))}")
        return v


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


class AlternativaUpdate(BaseModel):
    texto: str | None = None
    correta: bool | None = None
    ordem: int | None = None


class QuestaoReadWithAlternativas(QuestaoRead):
    alternativas: list[AlternativaRead] = []


class AvaliacaoReadWithQuestoes(AvaliacaoRead):
    questoes: list[QuestaoReadWithAlternativas] = []


class AlternativaResponderRead(BaseModel):
    id: int
    questao_id: int
    texto: str
    ordem: int = 0

    model_config = {"from_attributes": True}


class QuestaoResponderRead(BaseModel):
    id: int
    avaliacao_id: int
    enunciado: str
    tipo: str
    pontuacao: Decimal = Decimal("1.00")
    ordem: int = 0
    alternativas: list[AlternativaResponderRead] = []

    model_config = {"from_attributes": True}


class AvaliacaoResponderRead(BaseModel):
    id: int
    titulo: str
    descricao: str | None = None
    tipo: str
    tentativas_max: int = 3
    tempo_limite_min: int | None = None
    questoes: list[QuestaoResponderRead] = []

    model_config = {"from_attributes": True}


class RespostaSubmeterItem(BaseModel):
    questao_id: int
    alternativa_id: int | None = None
    resposta_texto: str | None = None


class SubmeterAvaliacaoRequest(BaseModel):
    respostas: list[RespostaSubmeterItem]
    iniciado_em: datetime | None = None


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
    pontuacao_atribuida: Decimal | None = None
    corrigida_por: uuid.UUID | None = None
    corrigida_em: datetime | None = None
    respondido_em: datetime

    model_config = {"from_attributes": True}

    @field_serializer("pontuacao_atribuida")
    def _serializar_pontuacao(self, v: Decimal | None) -> float | None:
        return float(v) if v is not None else None


class CorrecaoPendenteRead(BaseModel):
    resposta_id: int
    usuario_id: uuid.UUID
    usuario_nome: str | None = None
    questao_id: int
    enunciado: str
    resposta_texto: str | None = None
    pontuacao: Decimal
    tentativa_num: int
    respondido_em: datetime

    model_config = {"from_attributes": True}


class CorrecaoPendenteInboxRead(CorrecaoPendenteRead):
    avaliacao_id: int
    avaliacao_titulo: str
    curso_id: int | None = None
    curso_titulo: str | None = None
    unidade_id: int | None = None
    unidade_titulo: str | None = None


class CorrigirRespostaRequest(BaseModel):
    pontuacao_atribuida: Decimal


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
    aguardando_correcao: bool = False

    model_config = {"from_attributes": True}

    @field_serializer("nota")
    def _serializar_nota(self, v: Decimal) -> float:
        return float(v)


class EstatisticasAvaliacaoRead(BaseModel):
    total_tentativas: int
    total_aprovados: int
    media_nota: float
    taxa_aprovacao: float


class EstatisticaQuestaoRead(BaseModel):
    questao_id: int
    enunciado: str
    tipo: str
    pontuacao: Decimal = Decimal("1.00")
    respondida: int
    acertos: int
    taxa_acerto: float
    aguardando_correcao: int = 0


class ResultadoFeedbackAlternativa(BaseModel):
    id: int
    texto: str
    correta: bool
    escolhida: bool
    ordem: int = 0

    model_config = {"from_attributes": True}


class ResultadoFeedbackQuestao(BaseModel):
    id: int
    enunciado: str
    tipo: str
    pontuacao: Decimal = Decimal("1.00")
    pontuacao_obtida: Decimal = Decimal("0")
    resposta_texto: str | None = None
    pontuacao_atribuida: Decimal | None = None
    alternativas: list[ResultadoFeedbackAlternativa] = []
    explicacao: str | None = None

    @field_serializer("pontuacao", "pontuacao_obtida", "pontuacao_atribuida")
    def _serializar_pontos(self, v: Decimal | None) -> float | None:
        return float(v) if v is not None else None


class ResultadoFeedbackRead(BaseModel):
    resultado_id: int
    avaliacao_id: int
    nota: Decimal
    aprovado: bool
    tentativa_num: int
    tempo_gasto_seg: int | None = None
    realizado_em: datetime
    questoes: list[ResultadoFeedbackQuestao] = []
