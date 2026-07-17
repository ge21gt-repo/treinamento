"""Testes que não dependem de banco de dados — validam importes e estrutura."""

from app.main import app
from app.schemas.curso import InscricaoTrilhaRead, TrilhaProgressoRead
from app.services.rbac import Permissoes


def test_app_routes_loaded():
    assert len(app.routes) >= 4  # pelo menos docs routes
    included = sum(1 for r in app.routes if type(r).__name__ == "_IncludedRouter")
    assert included >= 16  # 16 routers incluidos


def test_schemas_have_from_attributes():
    assert InscricaoTrilhaRead.model_config.get("from_attributes") is True
    assert TrilhaProgressoRead.model_config.get("from_attributes") is True


def test_trail_rbac_permissions_exist():
    assert Permissoes.TRILHA_CRIAR == "trilha:criar"
    assert Permissoes.TRILHA_EDITAR == "trilha:editar"
    assert Permissoes.TRILHA_EXCLUIR == "trilha:excluir"
    assert Permissoes.TRILHA_INSCREVER == "trilha:inscrever"
    assert Permissoes.TRILHA_VER_PROGRESSO == "trilha:ver_progresso"
