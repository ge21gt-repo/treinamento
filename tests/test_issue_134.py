"""Issue #110 — stream do chat do curso.

O transporte ASGI do httpx nao entrega streaming (bufferiza ate a app terminar),
entao testamos o gerador e o resolvedor do Last-Event-ID diretamente.
"""

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.cursos import _last_id_inicial, _stream_eventos
from app.config import settings


class _RequestFake:
    """Request minima: headers + 'desconectado' para o gerador encerrar."""

    def __init__(self, headers=None):
        self.headers = headers or {}

    async def is_disconnected(self) -> bool:
        return True


async def _curso(client) -> int:
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso 134", "ordem": 0})
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


async def _mensagens(client, curso_id: int, quantidade: int) -> list[int]:
    ids = []
    for i in range(quantidade):
        r = await client.post(f"/api/v1/cursos/{curso_id}/chat", json={"texto": f"msg {i}"})
        assert r.status_code == status.HTTP_201_CREATED, r.text
        ids.append(r.json()["id"])
    return ids


async def _stream(curso_id: int, last_id: int, ultimas: int, headers=None) -> list[str]:
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as sessao:
            return [
                chunk
                async for chunk in _stream_eventos(
                    sessao, curso_id, last_id, ultimas, _RequestFake(headers)
                )
            ]
    finally:
        await engine.dispose()


def _ids(chunks: list[str]) -> list[int]:
    return [int(c.split("id: ", 1)[1].split("\n", 1)[0]) for c in chunks]


async def test_stream_manda_id_e_historico(client):
    curso_id = await _curso(client)
    ids = await _mensagens(client, curso_id, 3)

    chunks = await _stream(curso_id, 0, 50)

    assert _ids(chunks) == ids, chunks
    assert all(c.startswith("id: ") and "\ndata: " in c for c in chunks), chunks


async def test_ultimas_limita_o_historico_inicial(client):
    curso_id = await _curso(client)
    ids = await _mensagens(client, curso_id, 5)

    chunks = await _stream(curso_id, 0, 2)

    assert _ids(chunks) == ids[-2:], chunks


async def test_desde_id_pula_o_que_ja_foi_visto(client):
    curso_id = await _curso(client)
    ids = await _mensagens(client, curso_id, 5)

    chunks = await _stream(curso_id, ids[2], 50)

    assert _ids(chunks) == ids[3:], chunks


async def test_last_event_id_tem_precedencia(client):
    curso_id = await _curso(client)
    ids = await _mensagens(client, curso_id, 5)

    request = _RequestFake({"last-event-id": str(ids[3])})
    assert _last_id_inicial(request, 0) == ids[3]

    chunks = await _stream(curso_id, _last_id_inicial(request, 0), 50)
    assert _ids(chunks) == ids[4:], chunks


async def test_ultimas_zero_nao_reenvia_historico(client):
    curso_id = await _curso(client)
    await _mensagens(client, curso_id, 3)

    chunks = await _stream(curso_id, 0, 0)

    assert chunks == [], chunks


async def test_parametros_invalidos_422(client):
    curso_id = await _curso(client)

    r = await client.get(f"/api/v1/cursos/{curso_id}/chat/stream?desde_id=-1")
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    r = await client.get(f"/api/v1/cursos/{curso_id}/chat/stream?ultimas=201")
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
