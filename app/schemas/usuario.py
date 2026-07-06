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
    aceite_lgpd: bool = False


class UsuarioRegistro(UsuarioBase):
    """Schema especifico para registro de usuario com selecao de perfil"""
    senha: str
    perfil_solicitado: str  # administrador_geral, instrutor, gestor, participante
    aceite_lgpd: bool = False


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
