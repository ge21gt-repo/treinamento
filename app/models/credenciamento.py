import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SolicitacaoCredenciamento(Base):
    """Solicitação de credenciamento de usuário"""
    __tablename__ = "solicitacoes_credenciamento"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lms.usuarios.id", ondelete="CASCADE"),
        nullable=False
    )
    perfil_solicitado: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    solicitado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    avaliado_por: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lms.usuarios.id", ondelete="SET NULL"),
        nullable=True
    )
    avaliado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_rejeicao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relacionamentos
    usuario: Mapped["Usuario"] = relationship(
        "Usuario", back_populates="solicitacoes_credenciamento",
        foreign_keys=[usuario_id],
    )
    aprovacoes: Mapped[list["AprovacaoHierarquica"]] = relationship(
        "AprovacaoHierarquica",
        back_populates="solicitacao",
        cascade="all, delete-orphan"
    )


class AprovacaoHierarquica(Base):
    """Histórico de aprovações hierárquicas"""
    __tablename__ = "aprovacoes_hierarquicas"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solicitacao_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lms.solicitacoes_credenciamento.id", ondelete="CASCADE"),
        nullable=False
    )
    aprovador_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lms.usuarios.id", ondelete="SET NULL"),
        nullable=True
    )
    nivel_hierarquico: Mapped[str] = mapped_column(String(50), nullable=False)
    acao: Mapped[str] = mapped_column(String(20), nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    solicitacao: Mapped["SolicitacaoCredenciamento"] = relationship("SolicitacaoCredenciamento", back_populates="aprovacoes")
    aprovador: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[aprovador_id])
