"""Testes da issue #119: o aceite da LGPD nascia verdadeiro, e nao dava aceitar.

Dois relatos da Tatiana. O segundo, que a issue aponta: quem entra pelo
Keycloak nascia com aceite_lgpd=True - a plataforma registrava consentimento
que a pessoa nunca deu. O primeiro, que a issue da como sem causa no codigo:
o cadastro local exigia o aceite e descartava o valor, entao a tela de
Privacidade mostrava "pendente" para quem tinha marcado o termo.

A decisao de produto de 26/10 e que os usuarios que ja existem aceitam de novo.
Isso vale pela versao do termo, sem apagar o aceite antigo: linha antiga tem
versao nula, que nunca casa com a versao em vigor.

Quase tudo aqui usa `cliente_real`, e nao o `client` do conftest - a razao esta
no docstring do fixture.
"""

import os
import uuid
from datetime import datetime, timezone

import pytest_asyncio
from fastapi import status
from sqlalchemy import text

from app.api.deps import get_current_user
from app.config import settings
from app.main import app
from app.services.auth import create_access_token
from app.services.lgpd import aceite_pendente

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]

_ACEITE = "/api/v1/usuarios/me/aceite-lgpd"
_ME = "/api/v1/usuarios/me"
_PREFERENCIAS = "/api/v1/usuarios/me/preferencias"


class _SemOverride:
    """Faz o get_current_user de verdade rodar, mantendo o get_db do conftest."""

    def __enter__(self):
        self.anterior = app.dependency_overrides.pop(get_current_user, None)
        return self

    def __exit__(self, *exc):
        if self.anterior is not None:
            app.dependency_overrides[get_current_user] = self.anterior
        return False


def _cabecalho(user):
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def cliente_real(client, admin_user):
    """O `client` do conftest, mas com a cadeia real de autenticacao.

    O `client` substitui get_current_user por um objeto de usuario montado na
    fixture. Esse objeto esta preso a OUTRA sessao, e isso atrapalha de duas
    formas nesta issue:

    - `perfis` nunca foi carregado, e qualquer rota que serialize UsuarioRead
      (ou que leia current_user.perfis) tenta carregar a colecao na hora e cai
      em MissingGreenlet.
    - o que a rota altera no objeto nao e gravado, porque o commit da rota e de
      uma sessao a que ele nao pertence - o aceite parecia funcionar e o banco
      continuava sem nada.

    As duas coisas sao limitacao do atalho do fixture, nao das rotas: e assim
    que test_issue21_perfis.py ja testava /usuarios/me. Removendo so o override
    do usuario, o get_current_user de verdade carrega os perfis com selectinload
    e devolve um objeto da sessao da propria requisicao.
    """
    anterior = app.dependency_overrides.pop(get_current_user, None)
    client.headers.update(_cabecalho(admin_user))
    try:
        yield client
    finally:
        if anterior is not None:
            app.dependency_overrides[get_current_user] = anterior


async def _criar_usuario(email, *, aceite=False, versao=None, data_aceite=None):
    """Cria usuario direto no banco (o /auth/registro tem limite por minuto)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.usuario import Usuario

    eng = create_async_engine(_URL)
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessao:
            user = Usuario(
                id=uuid.uuid4(),
                nome_completo="Pessoa LGPD",
                email=email,
                ativo=True,
                status_credenciamento="aprovado",
                aceite_lgpd=aceite,
                data_aceite_lgpd=data_aceite,
                versao_termo_lgpd=versao,
            )
            sessao.add(user)
            await sessao.commit()
            return user
    finally:
        await eng.dispose()


async def _consultar(sql, parametros=None):
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_URL)
    try:
        async with eng.begin() as conn:
            return (await conn.execute(text(sql), parametros or {})).first()
    finally:
        await eng.dispose()


async def _linha_lgpd(email):
    linha = await _consultar(
        "SELECT aceite_lgpd, data_aceite_lgpd, versao_termo_lgpd, host(ip_aceite_lgpd) "
        "FROM lms.usuarios WHERE email = :e",
        {"e": email},
    )
    assert linha is not None, f"usuario {email} nao existe"
    return {
        "aceite_lgpd": linha[0],
        "data_aceite_lgpd": linha[1],
        "versao_termo_lgpd": linha[2],
        "ip": linha[3],
    }


class TestIssue119Provisionamento:
    """Item 1: ninguem nasce com aceite que nao deu."""

    async def test_usuario_do_keycloak_nasce_sem_aceite(self, client, monkeypatch):
        """O critério de aceite da issue, pelo caminho real do provisionamento."""
        sub = str(uuid.uuid4())
        email = f"kc.{sub[:8]}@test.com"

        def _token_falso(_token):
            return {"sub": sub, "email": email, "name": "Vindo do Keycloak"}

        monkeypatch.setattr("app.api.deps.validar_token_keycloak", _token_falso)

        with _SemOverride():
            r = await client.get(_ME)
            assert r.status_code == status.HTTP_200_OK, r.text
            corpo = r.json()

        assert corpo["email"] == email
        assert corpo["aceite_lgpd"] is False
        assert corpo["data_aceite_lgpd"] is None
        assert corpo["aceite_lgpd_pendente"] is True

        assert (await _linha_lgpd(email))["aceite_lgpd"] is False

    async def test_subordinado_nasce_sem_aceite(self, cliente_real):
        email = "subordinado119@test.com"
        r = await cliente_real.post(
            "/api/v1/usuarios/criar-subordinado",
            json={
                "nome_completo": "Subordinado 119",
                "email": email,
                "senha": "Teste123!",
                "perfil": "participante",
                "aceite_lgpd": True,
            },
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text
        assert r.json()["aceite_lgpd"] is False
        assert r.json()["aceite_lgpd_pendente"] is True

        assert (await _linha_lgpd(email))["aceite_lgpd"] is False

    async def test_criar_subordinado_nao_exige_mais_o_aceite(self, cliente_real):
        """Quem cria a conta nao consente pelo outro, entao o campo nao e exigido."""
        r = await cliente_real.post(
            "/api/v1/usuarios/criar-subordinado",
            json={
                "nome_completo": "Sem Aceite 119",
                "email": "semaceite119@test.com",
                "senha": "Teste123!",
                "perfil": "participante",
                "aceite_lgpd": False,
            },
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text


class TestIssue119CadastroLocal:
    """O primeiro relato da Tatiana, que a issue da como sem causa no codigo."""

    async def test_cadastro_local_grava_o_aceite(self, client):
        """Antes: a rota exigia o aceite e o descartava, e a linha nascia False."""
        email = f"local.{uuid.uuid4().hex[:8]}@test.com"
        r = await client.post(
            "/api/v1/auth/registro",
            json={
                "nome_completo": "Cadastro Local",
                "email": email,
                "senha": "Teste123!",
                "perfil_solicitado": "participante",
                "aceite_lgpd": True,
            },
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text

        linha = await _linha_lgpd(email)
        assert linha["aceite_lgpd"] is True, "marcou o termo no cadastro e nao foi gravado"
        assert linha["data_aceite_lgpd"] is not None
        assert linha["versao_termo_lgpd"] == settings.VERSAO_TERMO_LGPD


class TestIssue119RotaDeAceite:
    """Item 2: a rota do aceite, idempotente e so para o proprio usuario."""

    async def test_aceitar_grava_data_versao_e_ip(self, cliente_real):
        r = await cliente_real.post(_ACEITE, json={}, headers={"x-forwarded-for": "203.0.113.90"})
        assert r.status_code == status.HTTP_200_OK, r.text

        corpo = r.json()
        assert corpo["aceite_lgpd"] is True
        assert corpo["data_aceite_lgpd"] is not None
        assert corpo["versao_termo_lgpd"] == settings.VERSAO_TERMO_LGPD
        assert corpo["aceite_lgpd_pendente"] is False

        linha = await _linha_lgpd("admin@test.com")
        assert linha["aceite_lgpd"] is True
        assert linha["data_aceite_lgpd"] is not None
        assert linha["versao_termo_lgpd"] == settings.VERSAO_TERMO_LGPD
        assert linha["ip"] == "203.0.113.90"

    async def test_sem_corpo_usa_a_versao_em_vigor(self, cliente_real):
        r = await cliente_real.post(_ACEITE)
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["versao_termo_lgpd"] == settings.VERSAO_TERMO_LGPD

    async def test_aceitar_de_novo_nao_mexe_na_data(self, cliente_real):
        """Idempotente: a data e o fato juridico, nao pode ser reescrita a cada F5."""
        primeira = (await cliente_real.post(_ACEITE, json={})).json()["data_aceite_lgpd"]
        assert primeira is not None

        r = await cliente_real.post(_ACEITE, json={})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["data_aceite_lgpd"] == primeira

        assert (await _linha_lgpd("admin@test.com"))["data_aceite_lgpd"] is not None

    async def test_versao_nova_pede_aceite_de_novo(self, cliente_real, monkeypatch):
        await cliente_real.post(_ACEITE, json={"versao_termo": "1.0"})

        monkeypatch.setattr(settings, "VERSAO_TERMO_LGPD", "2.0")

        corpo = (await cliente_real.get(_ME)).json()
        assert corpo["aceite_lgpd"] is True, "o aceite anterior nao devia ser apagado"
        assert corpo["aceite_lgpd_pendente"] is True, "a versao nova devia pedir aceite"

        r = await cliente_real.post(_ACEITE, json={"versao_termo": "2.0"})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["aceite_lgpd_pendente"] is False
        assert (await _linha_lgpd("admin@test.com"))["versao_termo_lgpd"] == "2.0"

    async def test_aceite_gera_linha_de_auditoria(self, cliente_real):
        """Consentimento e fato juridico: entra no log_auditoria, que e imutavel."""
        antes = (await _consultar("SELECT count(*) FROM lms.log_auditoria WHERE acao = 'aceite_lgpd'"))[0]

        r = await cliente_real.post(_ACEITE, json={})
        assert r.status_code == status.HTTP_200_OK, r.text

        depois = (await _consultar("SELECT count(*) FROM lms.log_auditoria WHERE acao = 'aceite_lgpd'"))[0]
        assert depois == antes + 1

    async def test_versao_longa_recusada(self, cliente_real):
        r = await cliente_real.post(_ACEITE, json={"versao_termo": "v" * 51})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    async def test_o_formato_do_front_e_aceito(self, cliente_real):
        """O formato definido no comentario do Caua, de 23/10, tem 21 caracteres.

        Com a coluna em varchar(20) - como eu havia dimensionado - esta string
        levava 422 e nao caberia no banco. O teste existe para ninguem estreitar
        a coluna de novo.
        """
        versao = "provisoria-2026-10-22"
        assert len(versao) == 21

        r = await cliente_real.post(_ACEITE, json={"versao_termo": versao})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["versao_termo_lgpd"] == versao

        assert (await _linha_lgpd("admin@test.com"))["versao_termo_lgpd"] == versao

    async def test_campo_fora_do_schema_recusado(self, cliente_real):
        r = await cliente_real.post(_ACEITE, json={"aceite_lgpd": True})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    async def test_cada_um_aceita_so_por_si(self, cliente_real):
        """O id sai do token: nao ha como aceitar em nome de outra pessoa."""
        await _criar_usuario("outro.aceite119@test.com")

        await cliente_real.post(_ACEITE, json={})

        assert (await _linha_lgpd("admin@test.com"))["aceite_lgpd"] is True
        assert (await _linha_lgpd("outro.aceite119@test.com"))["aceite_lgpd"] is False


class TestIssue119ReAceite:
    """A decisao de produto: quem ja existe aceita de novo."""

    async def test_quem_aceitou_antes_da_versao_fica_pendente(self):
        """E o caso de todos os usuarios de hoje: aceite True e versao nula.

        O aceite antigo e a data continuam gravados - o re-aceite nao destroi a
        informacao de que a pessoa consentiu, e quando.
        """
        quando = datetime(2026, 1, 15, tzinfo=timezone.utc)
        await _criar_usuario("antigo119@test.com", aceite=True, data_aceite=quando)

        linha = await _linha_lgpd("antigo119@test.com")
        assert linha["aceite_lgpd"] is True
        assert linha["data_aceite_lgpd"].year == 2026
        assert linha["versao_termo_lgpd"] is None

        assert aceite_pendente(linha["aceite_lgpd"], linha["versao_termo_lgpd"]) is True

    async def test_versao_antiga_tambem_fica_pendente(self):
        assert aceite_pendente(True, "0.9") is True
        assert aceite_pendente(True, settings.VERSAO_TERMO_LGPD) is False
        assert aceite_pendente(False, settings.VERSAO_TERMO_LGPD) is True

    async def test_me_expoe_o_pendente_para_o_front(self, cliente_real):
        corpo = (await cliente_real.get(_ME)).json()
        assert "aceite_lgpd_pendente" in corpo, "o front precisa de um sinal unico"
        assert corpo["aceite_lgpd_pendente"] is True

        await cliente_real.post(_ACEITE, json={})

        assert (await cliente_real.get(_ME)).json()["aceite_lgpd_pendente"] is False


class TestIssue119Bloqueio:
    """Item 4 (opcional na issue): o 403 enquanto o aceite esta pendente."""

    async def test_desligado_por_padrao(self, client):
        """Nasce desligado: ligar sem a tela no front trancaria todo mundo fora."""
        assert settings.LGPD_BLOQUEIO_ATIVO is False

        pendente = await _criar_usuario("bloqueio.off119@test.com")
        with _SemOverride():
            r = await client.get(_PREFERENCIAS, headers=_cabecalho(pendente))
            assert r.status_code == status.HTTP_200_OK, r.text

    async def test_ligado_bloqueia_as_outras_rotas(self, client, monkeypatch):
        monkeypatch.setattr(settings, "LGPD_BLOQUEIO_ATIVO", True)

        pendente = await _criar_usuario("bloqueio.on119@test.com")
        with _SemOverride():
            r = await client.get(_PREFERENCIAS, headers=_cabecalho(pendente))
            assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
            assert "ceite" in r.json()["detail"]

    async def test_ligado_libera_o_me_e_o_aceite(self, client, monkeypatch):
        monkeypatch.setattr(settings, "LGPD_BLOQUEIO_ATIVO", True)

        pendente = await _criar_usuario("bloqueio.livre119@test.com")
        with _SemOverride():
            cabecalho = _cabecalho(pendente)

            r = await client.get(_ME, headers=cabecalho)
            assert r.status_code == status.HTTP_200_OK, r.text

            r = await client.post(_ACEITE, json={}, headers=cabecalho)
            assert r.status_code == status.HTTP_200_OK, r.text

            r = await client.get(_PREFERENCIAS, headers=cabecalho)
            assert r.status_code == status.HTTP_200_OK, "depois de aceitar nao se bloqueia mais"
