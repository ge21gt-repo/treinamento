import pytest
from fastapi import status

from app.main import app

pytestmark = pytest.mark.db


async def _criar_curso(client):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Forum", "descricao": "x", "ordem": 0})
    return r.json()["id"]


class TestModeracaoConteudo:
    async def test_topico_com_termo_bloqueado_422(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Discussao sobre eleicao", "conteudo": "texto"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "bloqueado" in r.json()["detail"].lower()

    async def test_topico_normal_criado(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Duvida sobre modulo 3", "conteudo": "nao entendi a unidade 2"},
        )
        assert r.status_code == status.HTTP_201_CREATED

    async def test_resposta_com_termo_bloqueado_422(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Topico normal", "conteudo": "conteudo ok"},
        )
        topico_id = r.json()["id"]
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "voto no candidato x"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "bloqueado" in r.json()["detail"].lower()


class TestModeracaoService:
    async def test_normalizar_remove_acentos(self):
        from app.services.moderacao import normalizar

        assert normalizar("Eleição Presidente") == "eleicao presidente"

    async def test_checar_conteudo_detecta_termo(self, db_clean):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.services.moderacao import checar_conteudo, seed_termos_default

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        try:
            await seed_termos_default(session)
            termo = await checar_conteudo(session, "vamos falar de eleicoes municipais")
            assert termo is not None
            termo2 = await checar_conteudo(session, "conteudo totalmente normal")
            assert termo2 is None
        finally:
            await session.close()
            await engine.dispose()
