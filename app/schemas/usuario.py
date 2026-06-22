import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


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


class UsuarioUpdate(BaseModel):
    nome_completo: str | None = None
    email: EmailStr | None = None
    orgao_instituicao: str | None = None
    cargo: str | None = None
    telefone: str | None = None
    avatar_url: str | None = None
    ativo: bool | None = None


class UsuarioRead(UsuarioBase):
    id: uuid.UUID
    ativo: bool
    aceite_lgpd: bool
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}


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
