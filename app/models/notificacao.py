"""Modelo de notificacoes (issue 28 — aviso de aula e plataforma)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Notificacao(Base):
    __tablename__ = "notificacoes"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    corpo: Mapped[str | None] = mapped_column(Text)
    referencia_tipo: Mapped[str | None] = mapped_column(String(50))
    referencia_id: Mapped[int | None] = mapped_column(Integer)
    lida: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))