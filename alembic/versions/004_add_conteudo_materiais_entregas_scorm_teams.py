"""Add conteudo, materiais, entregas, scorm, teams fields

Revision ID: 004
Revises: 003_add_aulas_chat_unidades
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004_add_conteudo_materiais_entregas_scorm_teams"
down_revision: Union[str, None] = "003_add_aulas_chat_unidades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Create conteudos table ###
    op.create_table(
        "conteudos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("unidade_id", sa.Integer(), sa.ForeignKey("lms.unidades.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tipo_midia", sa.String(30), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("url_arquivo", sa.Text(), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column("duracao_segundos", sa.Integer(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("criado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms.usuarios.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="lms",
    )

    # ### Create materiais_complementares table ###
    op.create_table(
        "materiais_complementares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("curso_id", sa.Integer(), sa.ForeignKey("lms.cursos.id", ondelete="CASCADE"), nullable=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("url_arquivo", sa.Text(), nullable=False),
        sa.Column("criado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms.usuarios.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="lms",
    )

    # ### Create entregas_atividade table ###
    op.create_table(
        "entregas_atividade",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("unidade_id", sa.Integer(), sa.ForeignKey("lms.unidades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms.usuarios.id"), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("url_arquivo", sa.Text(), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pendente'")),
        sa.Column("nota", sa.Numeric(5, 2), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="lms",
    )

    # ### Create pacotes_scorm table ###
    op.create_table(
        "pacotes_scorm",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("curso_id", sa.Integer(), sa.ForeignKey("lms.cursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("arquivo_url", sa.Text(), nullable=False),
        sa.Column("manifest_json", postgresql.JSONB(), nullable=True),
        sa.Column("scorm_version", sa.String(10), nullable=True),
        sa.Column("criado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms.usuarios.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="lms",
    )

    # ### Create tracking_scorm table ###
    op.create_table(
        "tracking_scorm",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms.usuarios.id"), nullable=False),
        sa.Column("pacote_id", sa.Integer(), sa.ForeignKey("lms.pacotes_scorm.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sco_id", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'nao_iniciado'")),
        sa.Column("score_raw", sa.Float(), nullable=True),
        sa.Column("score_max", sa.Float(), nullable=True),
        sa.Column("score_min", sa.Float(), nullable=True),
        sa.Column("lesson_status", sa.String(30), nullable=True),
        sa.Column("progresso_pct", sa.Float(), nullable=True),
        sa.Column("dados_cmi", postgresql.JSONB(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="lms",
    )

    # ### Add teams fields to aulas_sincronas ###
    op.add_column("aulas_sincronas", sa.Column("teams_meeting_id", sa.String(200), nullable=True), schema="lms")
    op.add_column("aulas_sincronas", sa.Column("gravacao_conteudo_id", sa.Integer(), nullable=True), schema="lms")
    op.create_foreign_key(
        "fk_aulas_sincronas_gravacao_conteudo",
        "aulas_sincronas", "conteudos",
        ["gravacao_conteudo_id"], ["id"],
        source_schema="lms", referent_schema="lms",
    )


def downgrade() -> None:
    op.drop_constraint("fk_aulas_sincronas_gravacao_conteudo", "aulas_sincronas", schema="lms")
    op.drop_column("aulas_sincronas", "gravacao_conteudo_id", schema="lms")
    op.drop_column("aulas_sincronas", "teams_meeting_id", schema="lms")
    op.drop_table("tracking_scorm", schema="lms")
    op.drop_table("pacotes_scorm", schema="lms")
    op.drop_table("entregas_atividade", schema="lms")
    op.drop_table("materiais_complementares", schema="lms")
    op.drop_table("conteudos", schema="lms")
