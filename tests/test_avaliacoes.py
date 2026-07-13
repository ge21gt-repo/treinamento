import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import status

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class TestAvaliacoesAuth:
    async def test_list_avaliacoes_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/avaliacoes")
        assert r.status_code in AUTH_OK

    async def test_create_avaliacao_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/avaliacoes", json={"titulo": "x", "tipo": "quiz"})
        assert r.status_code in AUTH_OK

    async def test_get_avaliacao_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/avaliacoes/1")
        assert r.status_code in AUTH_OK


class TestAvaliacoesCRUD:
    async def _setup(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso AV", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod AV", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid AV", "tipo": "conteudo", "ordem": 0})
        return r.json()["id"]

    async def test_create_and_get_avaliacao(self, client):
        uni_id = await self._setup(client)
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Prova Final", "tipo": "prova", "nota_minima": 70.0})
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["titulo"] == "Prova Final"
        av_id = data["id"]

        r = await client.get(f"/api/v1/avaliacoes/{av_id}")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Prova Final"

    async def test_update_avaliacao(self, client):
        uni_id = await self._setup(client)
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Original", "tipo": "quiz"})
        av_id = r.json()["id"]

        r = await client.patch(f"/api/v1/avaliacoes/{av_id}", json={"titulo": "Atualizado"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Atualizado"

    async def test_delete_avaliacao(self, client):
        uni_id = await self._setup(client)
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Pra Deletar", "tipo": "quiz"})
        av_id = r.json()["id"]

        r = await client.delete(f"/api/v1/avaliacoes/{av_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

        r = await client.get(f"/api/v1/avaliacoes/{av_id}")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_list_avaliacoes(self, client):
        r = await client.get("/api/v1/avaliacoes")
        assert r.status_code == status.HTTP_200_OK
        assert isinstance(r.json(), list)


class TestQuestoesAlternativas:
    async def _setup(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Q", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod Q", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid Q", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval Q", "tipo": "prova"})
        return r.json()["id"]

    async def test_create_questao_and_alternativas(self, client):
        av_id = await self._setup(client)

        r = await client.post("/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Quanto é 2+2?", "tipo": "multipla_escolha", "pontuacao": 10})
        assert r.status_code == status.HTTP_201_CREATED
        q_id = r.json()["id"]

        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "4", "correta": True, "ordem": 0})
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["correta"] is True

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/questoes")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.json()) == 1

        r = await client.get(f"/api/v1/avaliacoes/questoes/{q_id}/alternativas")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.json()) == 1

    async def test_update_questao(self, client):
        av_id = await self._setup(client)
        r = await client.post("/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Old", "tipo": "dissertativa"})
        q_id = r.json()["id"]

        r = await client.patch(f"/api/v1/avaliacoes/questoes/{q_id}", json={"enunciado": "Updated"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["enunciado"] == "Updated"


class TestRespostasResultados:
    async def test_register_resposta_and_resultado(self, client, admin_user):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso R", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod R", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid R", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval R", "tipo": "prova"})
        av_id = r.json()["id"]

        r = await client.post("/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Pergunta?", "tipo": "multipla_escolha"})
        q_id = r.json()["id"]

        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "Correta", "correta": True, "ordem": 0})
        alt_id = r.json()["id"]

        uid = str(admin_user.id)
        r = await client.post("/api/v1/avaliacoes/respostas", json={"usuario_id": uid, "questao_id": q_id, "alternativa_id": alt_id})
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["correta"] is True

        r = await client.post("/api/v1/avaliacoes/resultados", json={"usuario_id": uid, "avaliacao_id": av_id, "nota": 85.0, "aprovado": True})
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/avaliacoes/resultados/{uid}")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.json()) >= 1
