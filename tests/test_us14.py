import uuid
from uuid import uuid4

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


class TestTermosBloqueadosCRUD:
    async def test_listar_termos_seed(self, client):
        r = await client.get("/api/v1/comunicacao/forum/termos-bloqueados")
        assert r.status_code == status.HTTP_200_OK
        termos = r.json()
        assert len(termos) >= 1
        assert any(t["termo"] == "eleicao" for t in termos)

    async def test_criar_termo_novo(self, client):
        termo_unico = f"guerra-{uuid4()}"
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": termo_unico, "categoria": "improprio"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["termo"] == termo_unico

        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": f"topico sobre {termo_unico}", "conteudo": "x"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_criar_termo_duplicado_409(self, client):
        termo_unico = f"dup-{uuid4()}"
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": termo_unico},
        )
        assert r.status_code == status.HTTP_201_CREATED
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": termo_unico},
        )
        assert r.status_code == status.HTTP_409_CONFLICT

    async def test_excluir_termo(self, client):
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": f"excluir-{uuid4()}"},
        )
        termo_id = r.json()["id"]
        r = await client.delete(f"/api/v1/comunicacao/forum/termos-bloqueados/{termo_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT
        r = await client.get("/api/v1/comunicacao/forum/termos-bloqueados")
        assert all(t["id"] != termo_id for t in r.json())


class TestCRUDTopicoCompleto:
    async def test_criar_topico_curso_inexistente_404(self, client):
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": 999999999, "titulo": "topico", "conteudo": "conteudo"},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_topico_tem_autor_nome(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico autor", "conteudo": "conteudo"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["autor_nome"] != ""

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()[0]["autor_nome"] != ""

    async def test_listar_topicos_curso_inexistente_404(self, client):
        r = await client.get("/api/v1/comunicacao/forum/999999999")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_resposta_tem_autor_nome(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico resp", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "minha resposta"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["autor_nome"] != ""

    async def test_resposta_topico_inexistente_404(self, client):
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": 999999999, "conteudo": "resposta"},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND
