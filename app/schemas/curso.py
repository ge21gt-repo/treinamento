import uuid
from datetime import datetime


from pydantic import BaseModel


class TrilhaBase(BaseModel):
    titulo: str
    descricao: str | None = None
    imagem_capa_url: str | None = None
    nivel: str = "iniciante"
    carga_horaria_total: int | None = None
    publicada: bool = False


class TrilhaCreate(TrilhaBase):
    pass


class TrilhaUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    imagem_capa_url: str | None = None
    nivel: str | None = None
    carga_horaria_total: int | None = None
    publicada: bool | None = None


class TrilhaRead(TrilhaBase):
    id: int
    criado_por: uuid.UUID | None = None
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class CursoBase(BaseModel):
    trilha_id: int | None = None
    titulo: str
    descricao: str | None = None
    imagem_capa_url: str | None = None
    ordem: int = 0
    carga_horaria: int | None = None
    pre_requisito_curso_id: int | None = None
    publicado: bool = False
    instrutor_id: uuid.UUID | None = None


class CursoCreate(CursoBase):
    pass


class CursoUpdate(BaseModel):
    trilha_id: int | None = None
    titulo: str | None = None
    descricao: str | None = None
    imagem_capa_url: str | None = None
    ordem: int | None = None
    carga_horaria: int | None = None
    publicado: bool | None = None
    instrutor_id: uuid.UUID | None = None


class CursoRead(CursoBase):
    id: int
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


class ModuloBase(BaseModel):
    curso_id: int
    titulo: str
    descricao: str | None = None
    ordem: int = 0


class ModuloCreate(ModuloBase):
    pass


class ModuloUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    ordem: int | None = None


class ModuloRead(ModuloBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class UnidadeBase(BaseModel):
    modulo_id: int
    titulo: str
    tipo: str
    ordem: int = 0
    duracao_estimada: int | None = None
    conteudo_url: str | None = None
    url_externa: str | None = None


class UnidadeCreate(UnidadeBase):
    pass


class UnidadeUpdate(BaseModel):
    titulo: str | None = None
    tipo: str | None = None
    ordem: int | None = None
    duracao_estimada: int | None = None
    conteudo_url: str | None = None
    url_externa: str | None = None


class UnidadeRead(UnidadeBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class InscricaoCreate(BaseModel):
    usuario_id: uuid.UUID | None = None
    curso_id: int


class InscricaoRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    curso_id: int
    status: str
    progresso_pct: float
    data_inscricao: datetime
    data_conclusao: datetime | None = None
    nota_final: float | None = None

    model_config = {"from_attributes": True}


class ProgressoUnidadeBase(BaseModel):
    usuario_id: uuid.UUID
    unidade_id: int


class ProgressoUnidadeCreate(ProgressoUnidadeBase):
    pass


class ProgressoUnidadeUpdate(BaseModel):
    status: str | None = None
    tempo_gasto: int | None = None


class ProgressoUnidadeRead(ProgressoUnidadeBase):
    id: int
    status: str
    tempo_gasto: int
    concluido_em: datetime | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class AulaSincronaBase(BaseModel):
    curso_id: int
    titulo: str
    descricao: str | None = None
    data_hora: datetime
    link_externo: str | None = None
    duracao_minutos: int | None = None
    status: str = "agendada"
    teams_meeting_id: str | None = None


class AulaSincronaCreate(AulaSincronaBase):
    criar_reuniao_teams: bool = False


class AulaSincronaUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    data_hora: datetime | None = None
    link_externo: str | None = None
    duracao_minutos: int | None = None
    status: str | None = None


class AulaSincronaRead(AulaSincronaBase):
    id: int
    criado_por: uuid.UUID | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}


class MensagemCursoCreate(BaseModel):
    texto: str


class MensagemCursoRead(BaseModel):
    id: int
    curso_id: int
    usuario_id: str
    texto: str
    criado_em: datetime

    model_config = {"from_attributes": True}


class CursoArvoreItem(BaseModel):
    id: int
    titulo: str
    tipo: str
    ordem: int
    conteudo_url: str | None = None
    url_externa: str | None = None


class ModuloArvoreRead(BaseModel):
    id: int
    titulo: str
    ordem: int
    unidades: list[CursoArvoreItem]


class CursoArvoreRead(BaseModel):
    id: int
    titulo: str
    modulos: list[ModuloArvoreRead]


class ReorderItem(BaseModel):
    id: int
    ordem: int


class InscricaoTrilhaCreate(BaseModel):
    trilha_id: int


class InscricaoTrilhaRead(BaseModel):
    id: int
    usuario_id: uuid.UUID
    trilha_id: int
    status: str
    progresso_pct: float
    data_inscricao: datetime
    data_conclusao: datetime | None = None

    model_config = {"from_attributes": True}


class TrilhaProgressoRead(BaseModel):
    trilha_id: int
    titulo: str
    nivel: str
    carga_horaria_total: int | None = None
    total_cursos: int
    cursos_concluidos: int
    progresso_pct: float
    status: str
    data_inscricao: datetime | None = None
    data_conclusao: datetime | None = None

    model_config = {"from_attributes": True}
