import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TrilhaAprendizagem(Base):
    __tablename__ = "trilhas_aprendizagem"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    imagem_capa_url: Mapped[str | None] = mapped_column(Text)
    nivel: Mapped[str] = mapped_column(String(30), default="iniciante")
    carga_horaria_total: Mapped[int | None] = mapped_column(Integer)
    publicada: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cursos: Mapped[list["Curso"]] = relationship(back_populates="trilha")
    inscricoes: Mapped[list["InscricaoTrilha"]] = relationship(back_populates="trilha")


class Curso(Base):
    __tablename__ = "cursos"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trilha_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.trilhas_aprendizagem.id"))
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    imagem_capa_url: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    carga_horaria: Mapped[int | None] = mapped_column(Integer)
    pre_requisito_curso_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.cursos.id"))
    publicado: Mapped[bool] = mapped_column(Boolean, default=False)
    instrutor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    trilha: Mapped["TrilhaAprendizagem | None"] = relationship(back_populates="cursos")
    modulos: Mapped[list["Modulo"]] = relationship(back_populates="curso", cascade="all, delete-orphan")
    inscricoes: Mapped[list["Inscricao"]] = relationship(back_populates="curso")


class Modulo(Base):
    __tablename__ = "modulos"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curso_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.cursos.id", ondelete="CASCADE"), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    curso: Mapped["Curso"] = relationship(back_populates="modulos")
    unidades: Mapped[list["Unidade"]] = relationship(back_populates="modulo", cascade="all, delete-orphan")


class Unidade(Base):
    __tablename__ = "unidades"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    modulo_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.modulos.id", ondelete="CASCADE"), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    duracao_estimada: Mapped[int | None] = mapped_column(Integer)
    conteudo_url: Mapped[str | None] = mapped_column(Text)
    url_externa: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    modulo: Mapped["Modulo"] = relationship(back_populates="unidades")
    progresso: Mapped[list["ProgressoUnidade"]] = relationship(back_populates="unidade")


class Inscricao(Base):
    __tablename__ = "inscricoes"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    curso_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.cursos.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="inscrito")
    progresso_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    data_inscricao: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data_conclusao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nota_final: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    curso: Mapped["Curso"] = relationship(back_populates="inscricoes")


class ProgressoUnidade(Base):
    __tablename__ = "progresso_unidade"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    unidade_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.unidades.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="nao_iniciado")
    tempo_gasto: Mapped[int] = mapped_column(Integer, default=0)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unidade: Mapped["Unidade"] = relationship(back_populates="progresso")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MensagemCurso(Base):
    __tablename__ = "mensagens_curso"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curso_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.cursos.id", ondelete="CASCADE"), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    texto: Mapped[str] = mapped_column(String(2000), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AulaSincrona(Base):
    __tablename__ = "aulas_sincronas"
    __table_args__ = {"schema": "lms", "extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curso_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.cursos.id", ondelete="CASCADE"), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    link_externo: Mapped[str | None] = mapped_column(Text)
    duracao_minutos: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="agendada")
    teams_meeting_id: Mapped[str | None] = mapped_column(String(200))
    gravacao_conteudo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("lms.conteudos.id"))
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InscricaoTrilha(Base):
    __tablename__ = "inscricoes_trilha"
    __table_args__ = {"schema": "lms"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lms.usuarios.id"), nullable=False)
    trilha_id: Mapped[int] = mapped_column(Integer, ForeignKey("lms.trilhas_aprendizagem.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="inscrito")
    progresso_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    data_inscricao: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data_conclusao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trilha: Mapped["TrilhaAprendizagem"] = relationship(back_populates="inscricoes")
