import uuid
from datetime import datetime

from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Conteudo(Base):
    __tablename__ = "conteudos"
    __table_args__ = {"schema": "lms", "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unidade_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.unidades.id", ondelete="CASCADE"))
    tipo_midia: Mapped[str] = mapped_column(String(30), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    url_arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    tamanho_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duracao_segundos: Mapped[int | None] = mapped_column(Integer)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialComplementar(Base):
    __tablename__ = "materiais_complementares"
    __table_args__ = {"schema": "lms", "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curso_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.cursos.id", ondelete="CASCADE"))
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    url_arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EntregaAtividade(Base):
    __tablename__ = "entregas_atividade"
    __table_args__ = {"schema": "lms", "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unidade_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.unidades.id", ondelete="CASCADE"), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    url_arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    tamanho_bytes: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    nota: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    feedback: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
