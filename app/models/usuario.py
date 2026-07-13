import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = {"schema": "lms"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    cpf: Mapped[str | None] = mapped_column(String(14), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    orgao_instituicao: Mapped[str | None] = mapped_column(String(200))
    cargo: Mapped[str | None] = mapped_column(String(150))
    telefone: Mapped[str | None] = mapped_column(String(20))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    aceite_lgpd: Mapped[bool] = mapped_column(Boolean, default=False)
    data_aceite_lgpd: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_credenciamento: Mapped[str] = mapped_column(String(20), default="pendente")
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    data_aprovacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    perfis: Mapped[list["UsuarioPerfil"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan",
        foreign_keys="[UsuarioPerfil.usuario_id]",
    )
    solicitacoes_credenciamento: Mapped[list["SolicitacaoCredenciamento"]] = relationship(
        "SolicitacaoCredenciamento", back_populates="usuario", cascade="all, delete-orphan",
        foreign_keys="[SolicitacaoCredenciamento.usuario_id]",
    )


class Perfil(Base):
    __tablename__ = "perfis"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    permissoes: Mapped[dict | None] = mapped_column(JSONB, default={})
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuarios: Mapped[list["UsuarioPerfil"]] = relationship(back_populates="perfil")


class UsuarioPerfil(Base):
    __tablename__ = "usuario_perfil"
    __table_args__ = {"schema": "lms"}

    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id", ondelete="CASCADE"), primary_key=True)
    perfil_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.perfis.id", ondelete="CASCADE"), primary_key=True)
    atribuido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atribuido_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))

    usuario: Mapped["Usuario"] = relationship(back_populates="perfis", foreign_keys=[usuario_id])
    perfil: Mapped["Perfil"] = relationship(back_populates="usuarios")
