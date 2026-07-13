"""Tests for US-06: Upload e Gestão de Conteúdos Multimídia"""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.conteudo import (
    ConteudoBase,
    ConteudoCreate,
    ConteudoRead,
    ConteudoUpdate,
    MaterialComplementarBase,
    MaterialComplementarCreate,
    MaterialComplementarRead,
    MaterialComplementarUpdate,
    EntregaAtividadeBase,
    EntregaAtividadeCreate,
    EntregaAtividadeRead,
    EntregaAtividadeCorrigir,
)
from app.schemas.scorm import (
    PacoteScormBase,
    PacoteScormCreate,
    PacoteScormRead,
    TrackingScormCreate,
    TrackingScormRead,
    ScormLaunchResponse,
)
from app.services.rbac import Permissoes, has_permission
from app.services.storage import ALLOWED_MIME_TYPES, FLAT_ALLOWED


class TestConteudoSchemas:
    def test_conteudo_create_valid(self):
        data = ConteudoCreate(unidade_id=1, tipo_midia="video", titulo="Aula 1", url_arquivo="http://s3.com/video.mp4")
        assert data.tipo_midia == "video"
        assert data.ordem == 0

    def test_conteudo_create_no_url_fails(self):
        with pytest.raises(ValidationError):
            ConteudoCreate(unidade_id=1, tipo_midia="video", titulo="Aula 1")

    def test_conteudo_read_from_attributes(self):
        data = ConteudoRead(
            id=1,
            unidade_id=1,
            tipo_midia="pdf",
            titulo="Material",
            url_arquivo="http://s3.com/doc.pdf",
            criado_por=uuid.uuid4(),
            criado_em=datetime.now(),
        )
        assert data.id == 1
        assert data.model_config["from_attributes"]

    def test_conteudo_update_partial(self):
        data = ConteudoUpdate(titulo="Novo titulo")
        assert data.titulo == "Novo titulo"
        assert data.tipo_midia is None
        assert data.url_arquivo is None


class TestMaterialComplementarSchemas:
    def test_material_create_valid(self):
        data = MaterialComplementarCreate(curso_id=1, titulo="Apoio", tipo="pdf", url_arquivo="http://s3.com/doc.pdf")
        assert data.tipo == "pdf"

    def test_material_update_valid(self):
        data = MaterialComplementarUpdate(titulo="Atualizado", url_arquivo="http://s3.com/new.pdf")
        assert data.titulo == "Atualizado"

    def test_material_update_empty(self):
        data = MaterialComplementarUpdate()
        assert data.titulo is None
        assert data.tipo is None

    def test_material_read_from_attributes(self):
        data = MaterialComplementarRead(
            id=1,
            curso_id=1,
            titulo="Material",
            tipo="pdf",
            url_arquivo="http://s3.com/doc.pdf",
            criado_por=uuid.uuid4(),
            criado_em=datetime.now(),
        )
        assert data.model_config["from_attributes"]


class TestEntregaAtividadeSchemas:
    def test_entrega_create_valid(self):
        data = EntregaAtividadeCreate(
            unidade_id=1, titulo="Exercicio 1", url_arquivo="http://s3.com/exercicio.pdf"
        )
        assert data.titulo == "Exercicio 1"
        assert data.url_arquivo is not None

    def test_entrega_create_no_titulo_fails(self):
        with pytest.raises(ValidationError):
            EntregaAtividadeCreate(unidade_id=1, url_arquivo="http://s3.com/ex.pdf")

    def test_entrega_read_from_attributes(self):
        data = EntregaAtividadeRead(
            id=1,
            unidade_id=1,
            usuario_id=uuid.uuid4(),
            titulo="Entrega",
            url_arquivo="http://s3.com/ex.pdf",
            status="pendente",
            criado_em=datetime.now(),
        )
        assert data.status == "pendente"
        assert data.model_config["from_attributes"]

    def test_entrega_corrigir_valid(self):
        data = EntregaAtividadeCorrigir(nota=8.5, feedback="Muito bom")
        assert data.nota == 8.5
        assert data.feedback == "Muito bom"

    def test_entrega_corrigir_no_nota_fails(self):
        with pytest.raises(ValidationError):
            EntregaAtividadeCorrigir(feedback="Bom")


class TestScormSchemas:
    def test_pacote_create_valid(self):
        data = PacoteScormCreate(curso_id=1, titulo="Curso SCORM", arquivo_url="http://s3.com/curso.zip")
        assert data.titulo == "Curso SCORM"

    def test_pacote_read_from_attributes(self):
        data = PacoteScormRead(
            id=1,
            curso_id=1,
            titulo="SCORM",
            arquivo_url="http://s3.com/pacote.zip",
            criado_por=uuid.uuid4(),
            criado_em=datetime.now(),
        )
        assert data.model_config["from_attributes"]

    def test_tracking_create_valid(self):
        data = TrackingScormCreate(sco_id="sco1", status="concluido", score_raw=90.0, progresso_pct=100.0)
        assert data.score_raw == 90.0
        assert data.progresso_pct == 100.0

    def test_tracking_create_default_status(self):
        data = TrackingScormCreate(sco_id="sco1")
        assert data.status == "nao_iniciado"

    def test_scorm_launch_response(self):
        data = ScormLaunchResponse(url="http://player.com", token="abc123", sco_id="sco1")
        assert data.token == "abc123"


class TestRbacPermissions:
    def test_conteudo_permissions_exist(self):
        assert Permissoes.CONTEUDO_CRIAR == "conteudo:criar"
        assert Permissoes.CONTEUDO_VISUALIZAR == "conteudo:visualizar"
        assert Permissoes.MATERIAL_GERENCIAR == "material:gerenciar"
        assert Permissoes.ENTREGA_CRIAR == "entrega:criar"
        assert Permissoes.ENTREGA_CORRIGIR == "entrega:corrigir"
        assert Permissoes.SCORM_GERENCIAR == "scorm:gerenciar"
        assert Permissoes.SCORM_VISUALIZAR == "scorm:visualizar"

    def test_admin_geral_has_all_content_permissions(self):
        permissoes = [
            Permissoes.CONTEUDO_CRIAR,
            Permissoes.CONTEUDO_EDITAR,
            Permissoes.CONTEUDO_EXCLUIR,
            Permissoes.CONTEUDO_VISUALIZAR,
            Permissoes.MATERIAL_GERENCIAR,
        ]
        for p in permissoes:
            assert has_permission("administrador_geral", p), f"admin_geral should have {p}"

    def test_instrutor_has_content_permissions(self):
        permissoes = [
            Permissoes.CONTEUDO_CRIAR,
            Permissoes.CONTEUDO_EDITAR,
            Permissoes.CONTEUDO_EXCLUIR,
            Permissoes.CONTEUDO_VISUALIZAR,
            Permissoes.MATERIAL_GERENCIAR,
            Permissoes.ENTREGA_CORRIGIR,
            Permissoes.SCORM_GERENCIAR,
        ]
        for p in permissoes:
            assert has_permission("instrutor", p), f"instrutor should have {p}"

    def test_instrutor_has_material_permission(self):
        assert has_permission("instrutor", Permissoes.MATERIAL_GERENCIAR)

    def test_participante_has_entrega_criar(self):
        assert has_permission("participante", Permissoes.ENTREGA_CRIAR)
        assert has_permission("participante", Permissoes.ENTREGA_VISUALIZAR)

    def test_participante_cannot_corrigir(self):
        assert not has_permission("participante", Permissoes.ENTREGA_CORRIGIR)

    def test_gestor_has_visualizar_not_criar(self):
        assert has_permission("gestor", Permissoes.CONTEUDO_VISUALIZAR)
        assert not has_permission("gestor", Permissoes.CONTEUDO_CRIAR)


class TestStorageMimeTypes:
    def test_video_mime_types_allowed(self):
        assert "video/mp4" in FLAT_ALLOWED
        assert "video/webm" in FLAT_ALLOWED

    def test_pdf_allowed(self):
        assert "application/pdf" in FLAT_ALLOWED

    def test_scorm_allowed(self):
        assert "application/zip" in FLAT_ALLOWED

    def test_audio_allowed(self):
        assert "audio/mpeg" in FLAT_ALLOWED

    def test_invalid_mime_not_allowed(self):
        assert "text/html" not in FLAT_ALLOWED
        assert "application/x-msdownload" not in FLAT_ALLOWED
