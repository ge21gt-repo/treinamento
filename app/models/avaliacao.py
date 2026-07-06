import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Avaliacao(Base):
    __tablename__ = "avaliacoes"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unidade_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.unidades.id", ondelete="CASCADE"))
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    nota_minima: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("60.00"))
    tentativas_max: Mapped[int] = mapped_column(Integer, default=3)
    tempo_limite_min: Mapped[int | None] = mapped_column(Integer)
    peso: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    questoes: Mapped[list["Questao"]] = relationship(back_populates="avaliacao", cascade="all, delete-orphan")


class Questao(Base):
    __tablename__ = "questoes"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    avaliacao_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.avaliacoes.id", ondelete="CASCADE"), nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    pontuacao: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1.00"))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    explicacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    avaliacao: Mapped["Avaliacao"] = relationship(back_populates="questoes")
    alternativas: Mapped[list["Alternativa"]] = relationship(back_populates="questao", cascade="all, delete-orphan")


class Alternativa(Base):
    __tablename__ = "alternativas"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    questao_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.questoes.id", ondelete="CASCADE"), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    correta: Mapped[bool] = mapped_column(Boolean, default=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0)

    questao: Mapped["Questao"] = relationship(back_populates="alternativas")


class RespostaParticipante(Base):
    __tablename__ = "respostas_participante"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    questao_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.questoes.id"), nullable=False)
    alternativa_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.alternativas.id"))
    resposta_texto: Mapped[str | None] = mapped_column(Text)
    correta: Mapped[bool | None] = mapped_column(Boolean)
    tentativa_num: Mapped[int] = mapped_column(Integer, default=1)
    respondido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResultadoAvaliacao(Base):
    __tablename__ = "resultado_avaliacao"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    avaliacao_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.avaliacoes.id"), nullable=False)
    nota: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    aprovado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tentativa_num: Mapped[int] = mapped_column(Integer, default=1)
    tempo_gasto_seg: Mapped[int | None] = mapped_column(Integer)
    realizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
