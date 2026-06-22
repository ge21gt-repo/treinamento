import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ModeloCertificado(Base):
    __tablename__ = "modelos_certificado"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    template_html: Mapped[str] = mapped_column(Text, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text)
    assinatura_digital: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Certificado(Base):
    __tablename__ = "certificados"
    __table_args__ = {"schema": "lms"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    curso_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.cursos.id"), nullable=False)
    modelo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.modelos_certificado.id"))
    nota_final: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    carga_horaria: Mapped[int] = mapped_column(Integer, nullable=False)
    url_pdf: Mapped[str | None] = mapped_column(Text)
    qr_code_url: Mapped[str | None] = mapped_column(Text)
    hash_validacao: Mapped[str | None] = mapped_column(String(64), unique=True)
    emitido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valido_ate: Mapped[date | None] = mapped_column(Date)
