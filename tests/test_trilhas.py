import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_session
from app.main import app
from app.models.curso import TrilhaAprendizagem

pytestmark = pytest.mark.db


async def criar_trilha(client, titulo="Trilha Teste", nivel="iniciante", publicada=True):
    payload = {
        "titulo": titulo,
        "descricao": "Descricao da trilha de teste",
        "nivel": nivel,
        "publicada": publicada,
    }
    response = await client.post("/api/v1/trilhas", json=payload)
    return response


class TestTrilhasCRUD:
    async def test_criar_trilha(self, client):
        response = await criar_trilha(client)
        assert response.status_code == 201
        data = response.json()
        assert data["titulo"] == "Trilha Teste"
        assert data["nivel"] == "iniciante"
        assert data["publicada"] is True
        assert "id" in data

    async def test_listar_trilhas(self, client):
        await criar_trilha(client, "Trilha A")
        await criar_trilha(client, "Trilha B")
        response = await client.get("/api/v1/trilhas")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

    async def test_obter_trilha(self, client):
        criar_resp = await criar_trilha(client, "Trilha Unica")
        trilha_id = criar_resp.json()["id"]
        response = await client.get(f"/api/v1/trilhas/{trilha_id}")
        assert response.status_code == 200
        assert response.json()["titulo"] == "Trilha Unica"

    async def test_atualizar_trilha(self, client):
        criar_resp = await criar_trilha(client, "Trilha Original")
        trilha_id = criar_resp.json()["id"]
        response = await client.patch(
            f"/api/v1/trilhas/{trilha_id}",
            json={"titulo": "Trilha Atualizada"},
        )
        assert response.status_code == 200
        assert response.json()["titulo"] == "Trilha Atualizada"

    async def test_excluir_trilha(self, client):
        criar_resp = await criar_trilha(client, "Trilha Deletar")
        trilha_id = criar_resp.json()["id"]
        response = await client.delete(f"/api/v1/trilhas/{trilha_id}")
        assert response.status_code == 204

    async def test_trilha_nao_encontrada(self, client):
        response = await client.get("/api/v1/trilhas/99999")
        assert response.status_code == 404

    async def test_publicar_despublicar(self, client):
        criar_resp = await criar_trilha(client, "Trilha Publicar", publicada=False)
        trilha_id = criar_resp.json()["id"]
        assert criar_resp.json()["publicada"] is False

        response = await client.patch(
            f"/api/v1/trilhas/{trilha_id}",
            json={"publicada": True},
        )
        assert response.status_code == 200
        assert response.json()["publicada"] is True


class TestFiltroNivel:
    async def test_filtrar_por_nivel(self, client):
        await criar_trilha(client, "Iniciante 1", nivel="iniciante")
        await criar_trilha(client, "Iniciante 2", nivel="iniciante")
        await criar_trilha(client, "Avancado 1", nivel="avancado")

        response = await client.get("/api/v1/trilhas?nivel=iniciante")
        assert response.status_code == 200
        data = response.json()
        assert all(t["nivel"] == "iniciante" for t in data)

    async def test_filtrar_nivel_sem_resultados(self, client):
        await criar_trilha(client, "Teste", nivel="iniciante")
        response = await client.get("/api/v1/trilhas?nivel=intermediario")
        assert response.status_code == 200
        assert response.json() == []


class TestInscricaoTrilha:
    async def test_inscrever_em_trilha(self, client):
        criar_resp = await criar_trilha(client, "Trilha Inscricao")
        trilha_id = criar_resp.json()["id"]
        response = await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")
        assert response.status_code == 201
        data = response.json()
        assert data["trilha_id"] == trilha_id
        assert data["status"] == "inscrito"

    async def test_inscrever_duplicado(self, client):
        criar_resp = await criar_trilha(client, "Trilha Duplicada")
        trilha_id = criar_resp.json()["id"]
        await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")
        response = await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")
        assert response.status_code == 409

    async def test_minhas_trilhas(self, client):
        criar_resp = await criar_trilha(client, "Minha Trilha")
        trilha_id = criar_resp.json()["id"]
        await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")

        response = await client.get("/api/v1/trilhas/minhas-trilhas")
        assert response.status_code == 200
        data = response.json()
        assert any(t["trilha_id"] == trilha_id for t in data)

    async def test_progresso_trilha_sem_cursos(self, client):
        criar_resp = await criar_trilha(client, "Trilha Sem Cursos")
        trilha_id = criar_resp.json()["id"]
        await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")

        response = await client.get(f"/api/v1/trilhas/{trilha_id}/progresso")
        assert response.status_code == 200
        data = response.json()
        assert data["total_cursos"] == 0
        assert data["progresso_pct"] == 0.0

    async def test_progresso_trilha_sem_inscricao(self, client):
        criar_resp = await criar_trilha(client, "Trilha Sem Inscricao")
        trilha_id = criar_resp.json()["id"]
        response = await client.get(f"/api/v1/trilhas/{trilha_id}/progresso")
        assert response.status_code == 404
