import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SessaoAoVivo(Base):
    __tablename__ = "sessoes_ao_vivo"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curso_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.cursos.id"))
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    instrutor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    data_hora_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_hora_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="agendada")
    url_transmissao: Mapped[str | None] = mapped_column(Text)
    url_gravacao: Mapped[str | None] = mapped_column(Text)
    codigo_acesso: Mapped[str | None] = mapped_column(String(20))
    max_participantes: Mapped[int | None] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    presencas: Mapped[list["Presenca"]] = relationship(back_populates="sessao", cascade="all, delete-orphan")


class Presenca(Base):
    __tablename__ = "presenca"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sessao_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.sessoes_ao_vivo.id"), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    hora_entrada: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hora_saida: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tempo_permanencia_seg: Mapped[int | None] = mapped_column(Integer)
    presente: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_acesso: Mapped[str | None] = mapped_column(INET)

    sessao: Mapped["SessaoAoVivo"] = relationship(back_populates="presencas")
