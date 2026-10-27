"""Issue #127: nenhuma rota escrevia `Conteudo.disponivel`.

A coluna existia desde a issue 46 e o /consumo a respeitava desde a #111 -
quando falsa, o conteudo nao recebe URL e a tela mostra "Arquivo
indisponivel". Mas marcar ou desmarcar era UPDATE na mao no banco: o instrutor
que substituia um arquivo perdido nao tinha como limpar o aviso, e o dia em
que um bucket antigo voltasse exigiria acesso ao banco para reverter.

Opcao A da issue: o campo no PATCH /conteudos/{id}, com a permissao de editar
conteudo. O critério de aceite e conferido pelo /consumo, nao pela resposta do
PATCH - e lá que a tela lê.
"""

import os

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


class _ComoUsuario:
    """Troca o get_current_user e devolve o anterior no fim."""

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


async def _consultar(sql, parametros=None):
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_URL)
    try:
        async with eng.begin() as conn:
            return (await conn.execute(text(sql), parametros or {})).first()
    finally:
        await eng.dispose()


async def _curso_com_conteudo(client, titulo, url="uploads/video.mp4"):
    """Curso -> modulo -> unidade -> conteudo; devolve (curso_id, conteudo_id)."""
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
    assert r.status_code in (200, 201), r.text
    curso_id = r.json()["id"]
    r = await client.post(
        "/api/v1/cursos/modulos",
        json={"curso_id": curso_id, "titulo": "Mod", "descricao": "x", "ordem": 0},
    )
    mod_id = r.json()["id"]
    r = await client.post(
        "/api/v1/cursos/unidades",
        json={"modulo_id": mod_id, "titulo": "Unid", "tipo": "conteudo", "ordem": 0},
    )
    uni_id = r.json()["id"]
    r = await client.post(
        "/api/v1/conteudos",
        json={
            "unidade_id": uni_id,
            "tipo_midia": "video",
            "titulo": "Video",
            "url_arquivo": url,
            "ordem": 0,
        },
    )
    assert r.status_code in (200, 201), r.text
    return curso_id, r.json()["id"]


async def _do_consumo(client, curso_id, conteudo_id):
    """O conteudo como o /consumo o devolve: e onde a issue aponta."""
    r = await client.get(f"/api/v1/cursos/{curso_id}/consumo")
    assert r.status_code == status.HTTP_200_OK, r.text
    for m in r.json()["modulos"]:
        for u in m["unidades"]:
            for c in u["conteudos"]:
                if c["id"] == conteudo_id:
                    return c
    raise AssertionError(f"conteudo {conteudo_id} nao apareceu no /consumo")


class TestIssue127MarcarDisponibilidade:
    async def test_desmarcar_tira_a_url_do_consumo(self, client):
        """O critério de aceite, na direção de desmarcar."""
        curso_id, cid = await _curso_com_conteudo(client, "C127a")

        antes = await _do_consumo(client, curso_id, cid)
        assert antes["disponivel"] is True
        assert antes["url_arquivo"] is not None

        r = await client.patch(f"/api/v1/conteudos/{cid}", json={"disponivel": False})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["disponivel"] is False

        depois = await _do_consumo(client, curso_id, cid)
        assert depois["disponivel"] is False
        assert depois["url_arquivo"] is None

    async def test_remarcar_devolve_a_url(self, client):
        """E na direção de voltar - o bucket antigo que reaparece."""
        curso_id, cid = await _curso_com_conteudo(client, "C127b")

        await client.patch(f"/api/v1/conteudos/{cid}", json={"disponivel": False})
        assert (await _do_consumo(client, curso_id, cid))["url_arquivo"] is None

        r = await client.patch(f"/api/v1/conteudos/{cid}", json={"disponivel": True})
        assert r.status_code == status.HTTP_200_OK, r.text

        depois = await _do_consumo(client, curso_id, cid)
        assert depois["disponivel"] is True
        assert depois["url_arquivo"] is not None

    async def test_participante_recebe_403(self, client, participante_user):
        curso_id, cid = await _curso_com_conteudo(client, "C127c")

        with _ComoUsuario(participante_user):
            r = await client.patch(f"/api/v1/conteudos/{cid}", json={"disponivel": False})
        assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
        assert (await _do_consumo(client, curso_id, cid))["disponivel"] is True

    async def test_marcar_sem_arquivo_e_recusado(self, client):
        """Senao o /consumo prometeria uma URL assinada que nao existe."""
        curso_id, cid = await _curso_com_conteudo(client, "C127d")

        r = await client.patch(
            f"/api/v1/conteudos/{cid}", json={"disponivel": False, "url_arquivo": ""}
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.patch(f"/api/v1/conteudos/{cid}", json={"disponivel": True})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert (await _do_consumo(client, curso_id, cid))["disponivel"] is False

    async def test_trocar_o_arquivo_devolve_a_disponibilidade(self, client):
        """O caso do instrutor que substitui o arquivo perdido.

        A issue pede isso "se essa troca ja for possivel" - e e, pelo proprio
        PATCH, que sempre aceitou url_arquivo.
        """
        curso_id, cid = await _curso_com_conteudo(client, "C127e")

        await client.patch(f"/api/v1/conteudos/{cid}", json={"disponivel": False})
        assert (await _do_consumo(client, curso_id, cid))["disponivel"] is False

        r = await client.patch(
            f"/api/v1/conteudos/{cid}", json={"url_arquivo": "uploads/video-novo.mp4"}
        )
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["disponivel"] is True
        assert (await _do_consumo(client, curso_id, cid))["url_arquivo"] is not None

    async def test_disponivel_explicito_ganha_da_inferencia(self, client):
        """Mandar os dois: quem chamou sabe mais que a inferencia do arquivo."""
        _, cid = await _curso_com_conteudo(client, "C127f")

        r = await client.patch(
            f"/api/v1/conteudos/{cid}",
            json={"url_arquivo": "uploads/outro.mp4", "disponivel": False},
        )
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["disponivel"] is False

    async def test_a_mudanca_vai_para_a_auditoria(self, client):
        """A issue pede auditoria. conteudos.py nao auditava nada antes."""
        _, cid = await _curso_com_conteudo(client, "C127g")

        r = await client.patch(f"/api/v1/conteudos/{cid}", json={"disponivel": False})
        assert r.status_code == status.HTTP_200_OK, r.text

        linha = await _consultar(
            "SELECT dados_anteriores, dados_novos FROM lms.log_auditoria "
            "WHERE tabela_afetada = 'conteudos' AND registro_id = :r "
            "ORDER BY id DESC LIMIT 1",
            {"r": str(cid)},
        )
        assert linha is not None, "a alteracao do conteudo nao foi auditada"
        assert linha[0]["disponivel"] is True
        assert linha[1]["disponivel"] is False

    async def test_patch_sem_arquivo_e_sem_disponivel_continua_passando(self, client):
        """Nao regride: a conferencia do arquivo so vale quando se marca true.

        `disponivel` ja nasce true por default no modelo, entao um conteudo sem
        url_arquivo tendo o titulo editado nao pode comecar a levar 422. Por
        isso a conferencia olha o que o PEDIDO manda, e nao o estado final do
        objeto.

        O assert do PATCH de preparacao nao e enfeite: sem ele, a versao
        ingenua da regra fazia justamente esse PATCH virar 422, o conteudo
        continuava com arquivo, o PATCH seguinte passava e o teste ficava
        verde escondendo a quebra.
        """
        _, cid = await _curso_com_conteudo(client, "C127h")
        preparo = await client.patch(f"/api/v1/conteudos/{cid}", json={"url_arquivo": ""})
        assert preparo.status_code == status.HTTP_200_OK, preparo.text
        assert preparo.json()["url_arquivo"] == ""
        # Fica sem arquivo E disponivel - e o estado que a regra nao pode punir.
        assert preparo.json()["disponivel"] is True

        r = await client.patch(f"/api/v1/conteudos/{cid}", json={"titulo": "Outro titulo"})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["titulo"] == "Outro titulo"
