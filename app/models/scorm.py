import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PacoteScorm(Base):
    __tablename__ = "pacotes_scorm"
    __table_args__ = {"schema": "lms", "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curso_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.cursos.id", ondelete="CASCADE"), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    arquivo_url: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[dict | None] = mapped_column(JSONB)
    scorm_version: Mapped[str | None] = mapped_column(String(10))
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrackingScorm(Base):
    __tablename__ = "tracking_scorm"
    __table_args__ = {"schema": "lms", "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    pacote_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.pacotes_scorm.id", ondelete="CASCADE"), nullable=False)
    sco_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="nao_iniciado")
    score_raw: Mapped[float | None] = mapped_column(Float)
    score_max: Mapped[float | None] = mapped_column(Float)
    score_min: Mapped[float | None] = mapped_column(Float)
    lesson_status: Mapped[str | None] = mapped_column(String(30))
    progresso_pct: Mapped[float | None] = mapped_column(Float)
    dados_cmi: Mapped[dict | None] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
