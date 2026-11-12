"""Testes da issue #124 (titulo "Issue 100"): preferencias de interface.

Nao havia onde guardar preferencia de usuario: os tours de ajuda e o
menuRecolhido viviam no localStorage, entao quem trocava de navegador ou de
maquina via os tours de novo.

A mescla rasa e o ponto central. Um PUT do objeto inteiro faria duas abas (ou
dois dispositivos) apagarem a escolha uma da outra; por isso cada gravacao
mexe apenas nas chaves que envia, e null remove a chave.
"""

import json
import os
import uuid

from fastapi import status
from sqlalchemy import text

from app.api.deps import get_current_user
from app.main import app

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]

_ROTA = "/api/v1/usuarios/me/preferencias"


class _ComoUsuario:
    """Troca o get_current_user e devolve o anterior no fim.

    E assim que o conftest manda construir teste de outro papel: sobrescrever a
    dependencia, nao reautenticar por HTTP.
    """

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self.anterior = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides[get_current_user] = lambda: self.user
        return self.user

    def __exit__(self, *exc):
        if self.anterior is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = self.anterior
        return False


async def _criar_usuario(email):
    """Cria usuario direto no banco (o /auth/registro tem limite por minuto)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.usuario import Usuario

    eng = create_async_engine(_URL)
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessao:
            user = Usuario(
                id=uuid.uuid4(),
                nome_completo="Dono das Preferencias",
                email=email,
                ativo=True,
                aceite_lgpd=True,
                status_credenciamento="aprovado",
            )
            sessao.add(user)
            await sessao.commit()
            return user
    finally:
        await eng.dispose()


async def _consultar(sql, parametros=None):
    """Roda uma consulta com engine propria (padrao do conftest)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_URL)
    try:
        async with eng.begin() as conn:
            r = await conn.execute(text(sql), parametros or {})
            return r.scalar()
    finally:
        await eng.dispose()


def _payload_de_bytes(total, prefixo="enchimento"):
    """Monta um corpo de preferencias com aproximadamente `total` bytes."""
    return {"dados": {prefixo: "x" * total}}


class TestIssue124Leitura:
    """Item 2: quem nunca gravou recebe vazio, e sem criar linha."""

    async def test_sem_linha_devolve_vazio(self, client):
        r = await client.get(_ROTA)
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json() == {"dados": {}, "atualizado_em": None}

    async def test_leitura_nao_cria_linha(self, client):
        await client.get(_ROTA)
        assert await _consultar("SELECT count(*) FROM lms.usuario_preferencias") == 0


class TestIssue124MesclaRasa:
    """Criterio de aceite: duas gravacoes de chaves diferentes convivem."""

    async def test_duas_gravacoes_preservam_as_duas_chaves(self, client):
        r = await client.patch(_ROTA, json={"dados": {"tours": {"avaliacao-criar": "visto"}}})
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.patch(_ROTA, json={"dados": {"menuRecolhido": True}})
        assert r.status_code == status.HTTP_200_OK, r.text

        dados = (await client.get(_ROTA)).json()["dados"]
        assert dados == {"tours": {"avaliacao-criar": "visto"}, "menuRecolhido": True}

    async def test_null_remove_so_aquela_chave(self, client):
        await client.patch(_ROTA, json={"dados": {"menuRecolhido": True, "papelInicial": "instrutor"}})

        r = await client.patch(_ROTA, json={"dados": {"menuRecolhido": None}})
        assert r.status_code == status.HTTP_200_OK, r.text

        assert (await client.get(_ROTA)).json()["dados"] == {"papelInicial": "instrutor"}

    async def test_remover_chave_que_nao_existe_nao_falha(self, client):
        r = await client.patch(_ROTA, json={"dados": {"nunca-gravada": None}})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["dados"] == {}

    async def test_a_mescla_e_rasa_e_troca_o_objeto_inteiro(self, client):
        """Rasa, nao recursiva: o front e dono do conteudo de cada chave.

        Quem quiser somar um tour tem de mandar o objeto `tours` completo. E a
        regra que a issue pede, e o front depende dela.
        """
        await client.patch(_ROTA, json={"dados": {"tours": {"a": "visto", "b": "visto"}}})
        await client.patch(_ROTA, json={"dados": {"tours": {"c": "visto"}}})

        assert (await client.get(_ROTA)).json()["dados"] == {"tours": {"c": "visto"}}

    async def test_corpo_vazio_nao_mexe_em_nada(self, client):
        await client.patch(_ROTA, json={"dados": {"menuRecolhido": True}})

        r = await client.patch(_ROTA, json={"dados": {}})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["dados"] == {"menuRecolhido": True}

    async def test_gravacao_devolve_o_estado_e_a_data(self, client):
        r = await client.patch(_ROTA, json={"dados": {"menuRecolhido": True}})
        assert r.status_code == status.HTTP_200_OK, r.text
        corpo = r.json()
        assert corpo["dados"] == {"menuRecolhido": True}
        assert corpo["atualizado_em"] is not None


class TestIssue124Limites:
    """Item 4: forma e tamanho. O servidor nao interpreta o conteudo."""

    async def test_corpo_de_20kb_recusado(self, client):
        r = await client.patch(_ROTA, json=_payload_de_bytes(20 * 1024))
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    async def test_dentro_de_16kb_aceito(self, client):
        r = await client.patch(_ROTA, json=_payload_de_bytes(15 * 1024))
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_limite_vale_para_o_acumulado(self, client):
        """O limite e do que fica guardado, nao do corpo de uma requisicao.

        Duas gravacoes de 10 KB passam uma a uma mas somariam 20 KB na linha -
        o limite seria contornavel so dividindo a gravacao em duas.
        """
        r = await client.patch(_ROTA, json=_payload_de_bytes(10 * 1024, "primeira"))
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.patch(_ROTA, json=_payload_de_bytes(10 * 1024, "segunda"))
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

        dados = (await client.get(_ROTA)).json()["dados"]
        assert list(dados) == ["primeira"], "a gravacao recusada nao devia ter mexido na linha"

    async def test_acima_de_100_chaves_recusado(self, client):
        r = await client.patch(_ROTA, json={"dados": {f"chave{i}": i for i in range(101)}})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    async def test_cem_chaves_aceito(self, client):
        r = await client.patch(_ROTA, json={"dados": {f"chave{i}": i for i in range(100)}})
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_chave_com_caractere_invalido_recusada(self, client):
        r = await client.patch(_ROTA, json={"dados": {"menu recolhido": True}})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    async def test_chave_longa_recusada(self, client):
        r = await client.patch(_ROTA, json={"dados": {"c" * 65: True}})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    async def test_dados_precisa_ser_objeto(self, client):
        for corpo in ({"dados": "texto"}, {"dados": [1, 2]}, {"dados": None}):
            r = await client.patch(_ROTA, json=corpo)
            assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, (corpo, r.text)

    async def test_campo_fora_do_schema_recusado(self, client):
        r = await client.patch(_ROTA, json={"dados": {}, "usuario_id": str(uuid.uuid4())})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text


class TestIssue124Isolamento:
    """Item 5: so o proprio usuario le e grava as suas."""

    async def test_um_usuario_nao_ve_as_preferencias_do_outro(self, client):
        await client.patch(_ROTA, json={"dados": {"papelInicial": "administrador"}})

        outro = await _criar_usuario("preferencias.outro124@test.com")
        with _ComoUsuario(outro):
            r = await client.get(_ROTA)
            assert r.status_code == status.HTTP_200_OK, r.text
            assert r.json()["dados"] == {}, "viu a preferencia de outra pessoa"

            await client.patch(_ROTA, json={"dados": {"papelInicial": "participante"}})

        assert (await client.get(_ROTA)).json()["dados"] == {"papelInicial": "administrador"}
        assert await _consultar("SELECT count(*) FROM lms.usuario_preferencias") == 2

    async def test_a_linha_sai_junto_com_o_usuario(self, client):
        """ON DELETE CASCADE: preferencia nao sobrevive ao dono."""
        outro = await _criar_usuario("preferencias.cascade124@test.com")
        with _ComoUsuario(outro):
            await client.patch(_ROTA, json={"dados": {"menuRecolhido": True}})

        contagem = "SELECT count(*) FROM lms.usuario_preferencias WHERE usuario_id = :uid"
        assert await _consultar(contagem, {"uid": str(outro.id)}) == 1

        await _consultar("DELETE FROM lms.usuarios WHERE id = :uid RETURNING 1", {"uid": str(outro.id)})

        assert await _consultar(contagem, {"uid": str(outro.id)}) == 0


class TestIssue124SemAuditoria:
    """Item 6: preferencia de interface nao entra em log_auditoria."""

    async def test_gravar_preferencia_nao_gera_auditoria(self, client):
        antes = await _consultar("SELECT count(*) FROM lms.log_auditoria")

        r = await client.patch(_ROTA, json={"dados": {"tours": {"geral": "visto"}}})
        assert r.status_code == status.HTTP_200_OK, r.text

        assert await _consultar("SELECT count(*) FROM lms.log_auditoria") == antes


class TestIssue124Formato:
    """O servidor guarda o conteudo como veio, sem interpretar."""

    async def test_valores_aninhados_voltam_iguais(self, client):
        dados = {
            "tours": {"avaliacao-criar": "visto", "corrigir": {"passo": 3, "concluido": False}},
            "menu:estado": ["a", "b"],
            "papelInicial": "instrutor",
        }
        r = await client.patch(_ROTA, json={"dados": dados})
        assert r.status_code == status.HTTP_200_OK, r.text

        devolvido = (await client.get(_ROTA)).json()["dados"]
        assert json.dumps(devolvido, sort_keys=True) == json.dumps(dados, sort_keys=True)
