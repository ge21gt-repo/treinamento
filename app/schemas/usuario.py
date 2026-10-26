import json
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, computed_field, field_validator

from app.services.lgpd import aceite_pendente


class UsuarioBase(BaseModel):
    nome_completo: str
    email: EmailStr
    cpf: str | None = None
    orgao_instituicao: str | None = None
    cargo: str | None = None
    telefone: str | None = None
    avatar_url: str | None = None


class UsuarioCreate(UsuarioBase):
    senha: str
    perfil_solicitado: str = "participante"
    aceite_lgpd: bool = False


class UsuarioUpdate(BaseModel):
    nome_completo: str | None = None
    email: EmailStr | None = None
    orgao_instituicao: str | None = None
    cargo: str | None = None
    telefone: str | None = None
    avatar_url: str | None = None
    ativo: bool | None = None


class UsuarioUpdateMe(BaseModel):
    """Edicao do proprio cadastro (issue #94). So campos nao sensiveis.

    `extra = "forbid"` garante que email, ativo, cpf e perfis nunca passem por
    aqui, nem por engano.
    """
    model_config = {"extra": "forbid"}

    nome_completo: str | None = None
    telefone: str | None = None
    orgao_instituicao: str | None = None
    cargo: str | None = None
    avatar_url: str | None = None

    @field_validator("nome_completo")
    @classmethod
    def _nome_nao_nulo(cls, v):
        """Rejeita null/vazio explicito (correcao do dev, issue #94).

        O validador so roda quando o campo vem no corpo, entao PATCH sem
        nome_completo continua funcionando.
        """
        if v is None or not v.strip():
            raise ValueError("nome_completo nao pode ser vazio")
        return v


class UsuarioRead(UsuarioBase):
    id: uuid.UUID
    ativo: bool
    aceite_lgpd: bool
    data_aceite_lgpd: datetime | None = None
    versao_termo_lgpd: str | None = None
    criado_em: datetime
    atualizado_em: datetime
    perfis: list[str] = []

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def aceite_lgpd_pendente(self) -> bool:
        """Issue #119: um sinal unico para o front saber se precisa da tela.

        Separado de `aceite_lgpd` de proposito: aquele continua sendo o fato
        historico, com a data de quando a pessoa aceitou. Este diz se ainda
        falta aceitar a versao em vigor, e e por ele que o re-aceite decidido
        em produto chega a quem ja existia - sem o front ter de conhecer a
        versao do termo.
        """
        return aceite_pendente(self.aceite_lgpd, self.versao_termo_lgpd)

    @field_validator("perfis", mode="before")
    @classmethod
    def extract_perfis(cls, v):
        if v and isinstance(v, list) and v and hasattr(v[0], "perfil"):
            return [up.perfil.nome for up in v]
        return v or []


# Issue #124: limites das preferencias. O corpo nao e interpretado pelo
# servidor, entao o unico freio e forma e tamanho - sem isso o JSONB cresce sem
# limite com o que o front decidir mandar.
PREFERENCIAS_MAX_BYTES = 16 * 1024
PREFERENCIAS_MAX_CHAVES = 100
PREFERENCIAS_CHAVE_TAMANHO = 64
_PREFERENCIAS_CHAVE_RE = re.compile(r"^[A-Za-z0-9.:_-]{1,%d}$" % PREFERENCIAS_CHAVE_TAMANHO)


def validar_preferencias(dados: dict) -> None:
    """Valida forma e tamanho de um objeto de preferencias (issue #124).

    Fora do schema porque a rota precisa validar tambem o resultado da mescla,
    nao so o corpo recebido: duas gravacoes de 10 KB passariam uma a uma e
    deixariam 20 KB guardados.
    """
    if len(dados) > PREFERENCIAS_MAX_CHAVES:
        raise ValueError(f"maximo de {PREFERENCIAS_MAX_CHAVES} chaves em dados (recebido {len(dados)})")
    for chave in dados:
        if not isinstance(chave, str) or not _PREFERENCIAS_CHAVE_RE.match(chave):
            raise ValueError(
                f"chave invalida: {chave!r}. Use ate {PREFERENCIAS_CHAVE_TAMANHO} caracteres "
                "entre letras, numeros, ponto, hifen, sublinhado e dois-pontos"
            )
    tamanho = len(json.dumps(dados, ensure_ascii=False).encode("utf-8"))
    if tamanho > PREFERENCIAS_MAX_BYTES:
        raise ValueError(f"dados acima de {PREFERENCIAS_MAX_BYTES} bytes (recebido {tamanho})")


class PreferenciasUpdate(BaseModel):
    """Corpo do PATCH /usuarios/me/preferencias (issue #124).

    A mescla e rasa e feita na rota; aqui so se valida o que chegou. Valor
    `null` numa chave e pedido de remocao, por isso o dict aceita None.
    """

    model_config = {"extra": "forbid"}

    dados: dict

    @field_validator("dados")
    @classmethod
    def _validar(cls, v):
        validar_preferencias(v)
        return v


class PreferenciasRead(BaseModel):
    """Issue #124: quem nunca gravou recebe dados vazio e atualizado_em nulo."""

    dados: dict = {}
    atualizado_em: datetime | None = None

    model_config = {"from_attributes": True}


class AceiteLgpdRequest(BaseModel):
    """Corpo do POST /usuarios/me/aceite-lgpd (issue #119).

    A versao e opcional: sem ela vale a que esta em vigor no servidor. Assim o
    front manda exatamente o documento que exibiu, e um cliente simples nao
    precisa conhecer a versao.
    """

    model_config = {"extra": "forbid"}

    versao_termo: str | None = None

    @field_validator("versao_termo")
    @classmethod
    def _versao_curta(cls, v):
        if v is not None and (not v.strip() or len(v) > 20):
            raise ValueError("versao_termo deve ter de 1 a 20 caracteres")
        return v.strip() if v else v


class AceiteLgpdRead(BaseModel):
    """Resposta do aceite (issue #119).

    Nao devolve o UsuarioRead inteiro: o aceite nao muda perfil nem cadastro, e
    montar a resposta so com o que mudou evita serializar objeto ORM depois do
    commit - o caminho que virava 500 na #114.
    """

    aceite_lgpd: bool
    data_aceite_lgpd: datetime | None = None
    versao_termo_lgpd: str | None = None
    aceite_lgpd_pendente: bool


class PerfilBase(BaseModel):
    nome: str
    descricao: str | None = None
    permissoes: dict | None = None


class PerfilCreate(PerfilBase):
    pass


class PerfilRead(PerfilBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class UsuarioPerfilCreate(BaseModel):
    usuario_id: uuid.UUID
    perfil_id: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    sub: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


# Schemas especificos para Gestor
class GestorBase(BaseModel):
    """Campos base para gestor - extensivel para campos especificos no futuro"""

    pass


class GestorCreate(GestorBase, UsuarioCreate):
    """Schema para criacao de gestor - herda campos de usuario"""

    pass


class GestorRead(GestorBase, UsuarioRead):
    """Schema para leitura de gestor - herda campos de usuario"""

    pass


class GestorUpdate(GestorBase, UsuarioUpdate):
    """Schema para atualizacao de gestor - herda campos de usuario"""

    pass


class PerfilUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    permissoes: dict | None = None


class EsqueciSenhaRequest(BaseModel):
    email: EmailStr


class RedefinirSenhaRequest(BaseModel):
    token: str
    nova_senha: str


class CriarSubordinadoRequest(BaseModel):
    """Schema para gestor criar subordinado (participante)"""

    nome_completo: str
    email: EmailStr
    senha: str
    cpf: str | None = None
    orgao_instituicao: str | None = None
    cargo: str | None = None
    telefone: str | None = None
    perfil: str = "participante"
    aceite_lgpd: bool = False
