from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    # Nome exato da migration 21145d4bb9be.
    __table_args__ = (
        Index("ix_lms_usuarios_keycloak_sub", "keycloak_sub", unique=True),
        {"schema": "lms"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    cpf: Mapped[str | None] = mapped_column(String(14), unique=True)
    senha_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    orgao_instituicao: Mapped[str | None] = mapped_column(String(200))
    cargo: Mapped[str | None] = mapped_column(String(150))
    telefone: Mapped[str | None] = mapped_column(String(20), unique=True)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    aceite_lgpd: Mapped[bool] = mapped_column(Boolean, default=False)
    data_aceite_lgpd: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Issue #119: a versao aceita e o IP de quem aceitou. A versao e o que
    # permite o re-aceite sem destruir informacao: linha antiga tem null, que
    # nunca casa com a versao em vigor, e a data do aceite anterior continua
    # gravada. O historico completo fica em log_auditoria, que tem trigger de
    # imutabilidade - e o que serve como prova de consentimento.
    versao_termo_lgpd: Mapped[str | None] = mapped_column(String(50))
    ip_aceite_lgpd: Mapped[str | None] = mapped_column(INET)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_credenciamento: Mapped[str] = mapped_column(String(20), default="pendente")
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    data_aprovacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    silenciado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    keycloak_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(20), default="local", nullable=False, server_default="local")

    perfis: Mapped[list["UsuarioPerfil"]] = relationship(
        back_populates="usuario",
        cascade="all, delete-orphan",
        foreign_keys="[UsuarioPerfil.usuario_id]",
    )
    solicitacoes_credenciamento: Mapped[list["SolicitacaoCredenciamento"]] = relationship(
        "SolicitacaoCredenciamento",
        back_populates="usuario",
        cascade="all, delete-orphan",
        foreign_keys="[SolicitacaoCredenciamento.usuario_id]",
        primaryjoin="Usuario.id == SolicitacaoCredenciamento.usuario_id",
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


class UsuarioAulaSilenciado(Base):
    __tablename__ = "usuario_aula_silenciado"
    __table_args__ = (
        UniqueConstraint("usuario_id", "aula_id", name="uq_usuario_aula_silenciado"),
        {"schema": "lms"},
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lms.usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    aula_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lms.aulas_sincronas.id", ondelete="CASCADE"), primary_key=True
    )
    silenciado_ate: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsuarioPerfil(Base):
    __tablename__ = "usuario_perfil"
    __table_args__ = {"schema": "lms"}

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lms.usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    perfil_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.perfis.id", ondelete="CASCADE"), primary_key=True)
    atribuido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atribuido_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))

    usuario: Mapped["Usuario"] = relationship(back_populates="perfis", foreign_keys=[usuario_id])
    perfil: Mapped["Perfil"] = relationship(back_populates="usuarios")


class UsuarioPreferencias(Base):
    """Preferencias de interface, uma linha por usuario (issue #124).

    O conteudo e um JSONB sem esquema fixo: o front e dono do significado das
    chaves (tours vistos, menu recolhido, papel inicial). O servidor so valida
    forma e tamanho. Por isso nao ha coluna por preferencia - cada tour novo
    exigiria migration.

    PK = usuario_id: uma linha por pessoa, e o ON DELETE CASCADE leva as
    preferencias junto quando o usuario sai.
    """

    __tablename__ = "usuario_preferencias"
    __table_args__ = {"schema": "lms"}

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lms.usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    dados: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
