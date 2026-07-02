import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LogAcesso(Base):
    __tablename__ = "log_acesso"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acao: Mapped[str] = mapped_column(String(50), nullable=False)
    recurso_tipo: Mapped[str | None] = mapped_column(String(50))
    recurso_id: Mapped[int | None] = mapped_column(Integer)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    dispositivo: Mapped[str | None] = mapped_column(String(20))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acao: Mapped[str] = mapped_column(String(50), nullable=False)
    tabela_afetada: Mapped[str] = mapped_column(String(100), nullable=False)
    registro_id: Mapped[str] = mapped_column(String(100), nullable=False)
    dados_anteriores: Mapped[dict | None] = mapped_column(JSONB)
    dados_novos: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetricaEngajamento(Base):
    __tablename__ = "metricas_engajamento"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False)
    tempo_total_seg: Mapped[int] = mapped_column(Integer, default=0)
    conteudos_acessados: Mapped[int] = mapped_column(Integer, default=0)
    avaliacoes_realizadas: Mapped[int] = mapped_column(Integer, default=0)
    mensagens_enviadas: Mapped[int] = mapped_column(Integer, default=0)
    sessoes_assistidas: Mapped[int] = mapped_column(Integer, default=0)
    xp_ganho: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
