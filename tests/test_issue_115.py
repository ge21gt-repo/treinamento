"""Testes da issue #115 — cliente da Admin API do Keycloak (service account).

Tudo aqui é unitário: o `httpx` é trocado por `MockTransport`, então não há
banco nem Keycloak real. O que importa é o contrato: token cacheado, busca por
e-mail, criação devolvendo o `sub`, troca de role só nas `TRE_*` do client do
treinamento, `enabled`, e-mail de ação e erro do Keycloak sem vazar o corpo.
"""

import httpx
import pytest

from app.services import keycloak_admin as ka

_ASYNC_CLIENT_REAL = httpx.AsyncClient


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.setattr(ka.settings, "KEYCLOAK_SERVER", "https://kc.test")
    monkeypatch.setattr(ka.settings, "KEYCLOAK_REALM", "idesp-realm")
    monkeypatch.setattr(ka.settings, "KEYCLOAK_CLIENT_ID", "treinamento-front")
    monkeypatch.setattr(ka.settings, "KEYCLOAK_ADMIN_CLIENT_ID", "treinamento-backend")
    monkeypatch.setattr(ka.settings, "KEYCLOAK_ADMIN_CLIENT_SECRET", "segredo-admin")
    ka._resetar_cache()
    yield
    ka._resetar_cache()


def _mockar(monkeypatch, handler):
    """Instala um MockTransport e registra as chamadas feitas."""
    chamadas = []

    def handler_com_registro(request: httpx.Request) -> httpx.Response:
        chamadas.append((request.method, request.url.path, request.url.params, request.content))
        return handler(request)

    def fabrica(*args, **kwargs):
        kwargs.pop("timeout", None)
        return _ASYNC_CLIENT_REAL(transport=httpx.MockTransport(handler_com_registro))

    monkeypatch.setattr(ka.httpx, "AsyncClient", fabrica)
    return chamadas


def _token_ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 300})


async def test_token_de_servico_e_cacheado(monkeypatch):
    chamadas = _mockar(monkeypatch, _token_ok)

    primeiro = await ka._obter_token()
    segundo = await ka._obter_token()

    assert primeiro == segundo == "tok-123"
    assert len(chamadas) == 1, "o token deveria ser reaproveitado do cache"


async def test_buscar_usuario_por_email(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/token"):
            return _token_ok(request)
        assert request.url.params.get("exact") == "true"
        return httpx.Response(200, json=[{"id": "u1", "email": "a@b.com"}])

    _mockar(monkeypatch, handler)

    usuario = await ka.buscar_usuario_por_email("a@b.com")
    assert usuario == {"id": "u1", "email": "a@b.com"}


async def test_buscar_usuario_inexistente_devolve_none(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/token"):
            return _token_ok(request)
        return httpx.Response(200, json=[])

    _mockar(monkeypatch, handler)

    assert await ka.buscar_usuario_por_email("ninguem@b.com") is None


async def test_criar_usuario_devolve_o_sub(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/token"):
            return _token_ok(request)
        if request.method == "POST":
            return httpx.Response(201)
        return httpx.Response(200, json=[{"id": "novo-1", "email": "novo@b.com"}])

    _mockar(monkeypatch, handler)

    assert await ka.criar_usuario("novo@b.com", "Novo") == "novo-1"


async def test_definir_role_remove_as_antigas_e_poe_a_nova(monkeypatch):
    def handler(request):
        caminho = request.url.path
        if caminho.endswith("/token"):
            return _token_ok(request)
        if caminho.endswith("/admin/realms/idesp-realm/clients"):
            return httpx.Response(200, json=[{"id": "uuid-front", "clientId": "treinamento-front"}])
        if caminho.endswith("/clients/uuid-front/roles"):
            return httpx.Response(
                200,
                json=[
                    {"id": "r-adm", "name": "TRE_ADM"},
                    {"id": "r-gestor", "name": "TRE_GESTOR"},
                ],
            )
        if caminho.endswith("/users/sub1/role-mappings/clients/uuid-front"):
            if request.method == "GET":
                return httpx.Response(200, json=[{"id": "r-adm", "name": "TRE_ADM"}])
            return httpx.Response(204)
        return httpx.Response(404)

    chamadas = _mockar(monkeypatch, handler)

    await ka.definir_role("sub1", "gestor")

    rotas = [(metodo, caminho) for metodo, caminho, _params, _corpo in chamadas]
    alvo = "/admin/realms/idesp-realm/users/sub1/role-mappings/clients/uuid-front"
    assert ("DELETE", alvo) in rotas, "TRE_ADM antiga deveria ser removida"
    assert ("POST", alvo) in rotas, "TRE_GESTOR nova deveria ser adicionada"


async def test_definir_role_nao_duplica_a_role_atual(monkeypatch):
    def handler(request):
        caminho = request.url.path
        if caminho.endswith("/token"):
            return _token_ok(request)
        if caminho.endswith("/admin/realms/idesp-realm/clients"):
            return httpx.Response(200, json=[{"id": "uuid-front", "clientId": "treinamento-front"}])
        if caminho.endswith("/clients/uuid-front/roles"):
            return httpx.Response(200, json=[{"id": "r-gestor", "name": "TRE_GESTOR"}])
        if caminho.endswith("/users/sub1/role-mappings/clients/uuid-front"):
            return httpx.Response(200, json=[{"id": "r-gestor", "name": "TRE_GESTOR"}])
        return httpx.Response(404)

    chamadas = _mockar(monkeypatch, handler)

    await ka.definir_role("sub1", "gestor")

    # Considera só as chamadas de role-mapping (o POST do /token não conta).
    metodos = [
        metodo
        for metodo, caminho, _params, _corpo in chamadas
        if caminho.endswith("/role-mappings/clients/uuid-front")
    ]
    assert "DELETE" not in metodos
    assert "POST" not in metodos


async def test_definir_habilitado_manda_enabled(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/token"):
            return _token_ok(request)
        return httpx.Response(204)

    chamadas = _mockar(monkeypatch, handler)

    await ka.definir_habilitado("sub1", False)

    corpo = [corpo for metodo, _c, _p, corpo in chamadas if metodo == "PUT"][-1]
    assert b"enabled" in corpo and b"false" in corpo


async def test_enviar_email_de_acao_usa_as_acoes_padrao(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/token"):
            return _token_ok(request)
        return httpx.Response(204)

    chamadas = _mockar(monkeypatch, handler)

    await ka.enviar_email_de_acao("sub1")

    corpo = [corpo for metodo, _c, _p, corpo in chamadas if metodo == "PUT"][-1]
    assert b"UPDATE_PASSWORD" in corpo and b"VERIFY_EMAIL" in corpo


async def test_erro_do_keycloak_nao_vaza_o_corpo(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/token"):
            return _token_ok(request)
        return httpx.Response(500, json={"errorMessage": "DETALHE-INTERNO-SECRETO"})

    _mockar(monkeypatch, handler)

    with pytest.raises(ka.KeycloakAdminError) as erro:
        await ka.buscar_usuario_por_email("a@b.com")

    assert "DETALHE-INTERNO-SECRETO" not in str(erro.value)


async def test_sem_configuracao_levanta_erro(monkeypatch):
    monkeypatch.setattr(ka.settings, "KEYCLOAK_ADMIN_CLIENT_SECRET", "")

    with pytest.raises(ka.KeycloakAdminError):
        await ka._obter_token()
