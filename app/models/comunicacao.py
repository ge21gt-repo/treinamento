import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MensagemChat(Base):
    __tablename__ = "mensagens_chat"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sessao_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.sessoes_ao_vivo.id"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), default="texto")
    enviado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForumTopico(Base):
    __tablename__ = "forum_topicos"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curso_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.cursos.id"), nullable=False)
    autor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    fixado: Mapped[bool] = mapped_column(Boolean, default=False)
    fechado: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    respostas: Mapped[list["ForumResposta"]] = relationship(back_populates="topico", cascade="all, delete-orphan")


class ForumResposta(Base):
    __tablename__ = "forum_respostas"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topico_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.forum_topicos.id", ondelete="CASCADE"), nullable=False)
    autor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    resposta_pai_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.forum_respostas.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topico: Mapped["ForumTopico"] = relationship(back_populates="respostas")
