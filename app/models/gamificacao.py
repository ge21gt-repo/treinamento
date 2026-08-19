import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Nivel(Base):
    __tablename__ = "niveis"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    xp_minimo: Mapped[int] = mapped_column(Integer, nullable=False)
    icone_url: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)


class PontosXP(Base):
    __tablename__ = "pontos_xp"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[str] = mapped_column(String(50), nullable=False)
    referencia_id: Mapped[int | None] = mapped_column(Integer)
    descricao: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Badge(Base):
    __tablename__ = "badges"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    icone_url: Mapped[str | None] = mapped_column(Text)
    criterio_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    criterio_valor: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsuarioBadge(Base):
    __tablename__ = "usuario_badge"
    __table_args__ = {"schema": "lms"}

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lms.usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    badge_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.badges.id", ondelete="CASCADE"), primary_key=True)
    conquistado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Missao(Base):
    __tablename__ = "missoes"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    xp_recompensa: Mapped[int] = mapped_column(Integer, nullable=False)
    criterio: Mapped[dict] = mapped_column(JSONB, nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsuarioMissao(Base):
    __tablename__ = "usuario_missao"
    __table_args__ = (
        UniqueConstraint("usuario_id", "missao_id", name="uq_usuario_missao"),
        {"schema": "lms"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    missao_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.missoes.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="em_andamento")
    progresso_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Streak(Base):
    __tablename__ = "streaks"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), unique=True, nullable=False
    )
    dias_consecutivos: Mapped[int] = mapped_column(Integer, default=0)
    maior_streak: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_acesso_dia: Mapped[date | None] = mapped_column(Date)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
