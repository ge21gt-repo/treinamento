"""Issue #128: as rotas de reorder de modulos e unidades nao conferiam nada.

Aceitavam id repetido (o ultimo valor vencia), id inexistente (ignorado em
silencio, devolvendo 204 - o front achava que reordenou tudo) e itens de
modulos ou cursos diferentes, renumerando como se fossem do mesmo pai.

A rota de questoes (`PATCH /avaliacoes/questoes/reorder`, #108) foi feita a
partir destas e ja conferia as tres coisas; o comentario dela ate aponta esta
falta. Aqui as duas passam a fazer o mesmo.

Cada caso de recusa relê as ordens do banco, porque o que a issue pede nao e
so o 422: e que nada tenha sido aplicado.
"""

import os

from fastapi import status
from sqlalchemy import text

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]

_REORDER_UNIDADES = "/api/v1/cursos/unidades/reorder"
_REORDER_MODULOS = "/api/v1/cursos/modulos/reorder"


async def _consultar(sql, parametros=None):
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_URL)
    try:
        async with eng.begin() as conn:
            return (await conn.execute(text(sql), parametros or {})).first()
    finally:
        await eng.dispose()


async def _curso(client, titulo):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _modulo(client, curso_id, titulo, ordem=0):
    r = await client.post(
        "/api/v1/cursos/modulos",
        json={"curso_id": curso_id, "titulo": titulo, "descricao": "x", "ordem": ordem},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _unidade(client, modulo_id, titulo, ordem=0):
    r = await client.post(
        "/api/v1/cursos/unidades",
        json={"modulo_id": modulo_id, "titulo": titulo, "tipo": "conteudo", "ordem": ordem},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _ordens(tabela, ids):
    """{id: ordem} lido do banco, para provar que nada foi aplicado."""
    fora = {}
    for i in ids:
        linha = await _consultar(f"SELECT ordem FROM lms.{tabela} WHERE id = :i", {"i": i})
        fora[i] = linha[0] if linha else None
    return fora


class TestIssue128ReorderUnidades:
    """Os quatro casos do critério de aceite, para unidades."""

    async def test_caso_feliz_continua_funcionando(self, client):
        mod = await _modulo(client, await _curso(client, "C128a"), "Mod")
        a = await _unidade(client, mod, "A", ordem=0)
        b = await _unidade(client, mod, "B", ordem=1)

        r = await client.patch(_REORDER_UNIDADES, json=[{"id": a, "ordem": 1}, {"id": b, "ordem": 0}])
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text
        assert await _ordens("unidades", [a, b]) == {a: 1, b: 0}

    async def test_unidade_de_outro_modulo_recusada(self, client):
        curso_id = await _curso(client, "C128b")
        mod1 = await _modulo(client, curso_id, "Mod1", ordem=0)
        mod2 = await _modulo(client, curso_id, "Mod2", ordem=1)
        a = await _unidade(client, mod1, "A", ordem=0)
        forasteira = await _unidade(client, mod2, "B", ordem=0)

        r = await client.patch(
            _REORDER_UNIDADES, json=[{"id": a, "ordem": 5}, {"id": forasteira, "ordem": 9}]
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await _ordens("unidades", [a, forasteira]) == {a: 0, forasteira: 0}

    async def test_id_inexistente_recusado(self, client):
        mod = await _modulo(client, await _curso(client, "C128c"), "Mod")
        a = await _unidade(client, mod, "A", ordem=0)

        r = await client.patch(
            _REORDER_UNIDADES, json=[{"id": a, "ordem": 7}, {"id": 99999999, "ordem": 1}]
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        # Antes isto devolvia 204 e aplicava a ordem 7 na unidade A.
        assert await _ordens("unidades", [a]) == {a: 0}

    async def test_id_repetido_recusado(self, client):
        mod = await _modulo(client, await _curso(client, "C128d"), "Mod")
        a = await _unidade(client, mod, "A", ordem=0)
        b = await _unidade(client, mod, "B", ordem=1)

        r = await client.patch(
            _REORDER_UNIDADES,
            json=[{"id": a, "ordem": 3}, {"id": a, "ordem": 4}, {"id": b, "ordem": 5}],
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await _ordens("unidades", [a, b]) == {a: 0, b: 1}


class TestIssue128ReorderModulos:
    """Os mesmos quatro, para módulos - o pai aqui é o curso."""

    async def test_caso_feliz_continua_funcionando(self, client):
        curso_id = await _curso(client, "C128e")
        a = await _modulo(client, curso_id, "A", ordem=0)
        b = await _modulo(client, curso_id, "B", ordem=1)

        r = await client.patch(_REORDER_MODULOS, json=[{"id": a, "ordem": 1}, {"id": b, "ordem": 0}])
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text
        assert await _ordens("modulos", [a, b]) == {a: 1, b: 0}

    async def test_modulo_de_outro_curso_recusado(self, client):
        a = await _modulo(client, await _curso(client, "C128f"), "A", ordem=0)
        forasteiro = await _modulo(client, await _curso(client, "C128g"), "B", ordem=0)

        r = await client.patch(
            _REORDER_MODULOS, json=[{"id": a, "ordem": 5}, {"id": forasteiro, "ordem": 9}]
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await _ordens("modulos", [a, forasteiro]) == {a: 0, forasteiro: 0}

    async def test_id_inexistente_recusado(self, client):
        a = await _modulo(client, await _curso(client, "C128h"), "A", ordem=0)

        r = await client.patch(
            _REORDER_MODULOS, json=[{"id": a, "ordem": 7}, {"id": 99999999, "ordem": 1}]
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await _ordens("modulos", [a]) == {a: 0}

    async def test_id_repetido_recusado(self, client):
        curso_id = await _curso(client, "C128i")
        a = await _modulo(client, curso_id, "A", ordem=0)
        b = await _modulo(client, curso_id, "B", ordem=1)

        r = await client.patch(
            _REORDER_MODULOS,
            json=[{"id": a, "ordem": 3}, {"id": a, "ordem": 4}, {"id": b, "ordem": 5}],
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await _ordens("modulos", [a, b]) == {a: 0, b: 1}
