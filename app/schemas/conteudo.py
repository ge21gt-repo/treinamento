import uuid
from datetime import datetime

from pydantic import BaseModel, computed_field, field_validator

from app.services.storage import resolve_file_url


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
    # Issue #127: ninguem escrevia `disponivel`. A coluna existia desde a issue
    # 46, o /consumo a respeitava desde a #111, e marcar ou desmarcar era
    # UPDATE na mao - o instrutor que trocava um arquivo perdido nao tinha como
    # limpar o aviso de "Arquivo indisponivel".
    disponivel: bool | None = None


class ConteudoRead(ConteudoBase):
    id: int
    criado_por: uuid.UUID | None = None
    criado_em: datetime
    disponivel: bool = True
    # Issue #102: contexto para a busca levar a pessoa ate o conteudo.
    curso_id: int | None = None
    curso_titulo: str | None = None
    unidade_titulo: str | None = None
    # Issue #110: a busca marca com o selo "Rascunho" o conteudo de curso nao
    # publicado, como ja faz com curso e trilha. None = conteudo sem curso.
    curso_publicado: bool | None = None

    @computed_field
    @property
    def url_acesso(self) -> str | None:
        # Nao gera (nem tenta) URL assinada pra um arquivo que sabidamente nao
        # existe mais -- a tela recebe null em vez de um link morto (issue 46).
        if not self.disponivel:
            return None
        return resolve_file_url(self.url_arquivo)

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

    @computed_field
    @property
    def url_acesso(self) -> str:
        return resolve_file_url(self.url_arquivo)

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

    @computed_field
    @property
    def url_acesso(self) -> str:
        return resolve_file_url(self.url_arquivo)

    model_config = {"from_attributes": True}


class EntregaAtividadeCorrigir(BaseModel):
    """Issue #106: nota opcional, devolutiva obrigatoria. O aluno pode enviar um
    arquivo so para o instrutor ver, sem avaliacao formal."""

    nota: float | None = None
    feedback: str

    @field_validator("feedback")
    @classmethod
    def _feedback_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("feedback e obrigatorio")
        return v


# --- Chunked Upload ---


class IniciarUploadChunkedRequest(BaseModel):
    filename: str
    folder: str
    total_chunks: int


class IniciarUploadChunkedResponse(BaseModel):
    upload_id: str
    filename: str
    folder: str
    total_chunks: int


class UploadChunkedStatusResponse(BaseModel):
    upload_id: str
    total_chunks: int
    received_chunks: list[int]
    missing_chunks: list[int]
    complete: bool
