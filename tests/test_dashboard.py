import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class TestDashboardAuth:
    async def test_resumo_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/dashboard/resumo")
        assert r.status_code in AUTH_OK

    async def test_meu_progresso_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/dashboard/meu-progresso")
        assert r.status_code in AUTH_OK

    async def test_metricas_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/dashboard/metricas/00000000-0000-0000-0000-000000000001")
        assert r.status_code in AUTH_OK

    async def test_logs_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/dashboard/logs")
        assert r.status_code in AUTH_OK

    async def test_curso_stats_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/dashboard/cursos/1/stats")
        assert r.status_code in AUTH_OK


class TestDashboardResumo:
    async def test_resumo_retorna_estrutura(self, client):
        r = await client.get("/api/v1/dashboard/resumo")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        chaves = {
            "total_usuarios",
            "total_cursos",
            "total_trilhas",
            "total_inscricoes",
            "total_certificados",
            "total_sessoes_ao_vivo",
        }
        assert chaves.issubset(data.keys())
        assert isinstance(data["total_usuarios"], int)

    async def test_resumo_reflete_dados_criados(self, client):
        await client.post("/api/v1/cursos", json={"titulo": "Curso Dash", "descricao": "x", "ordem": 0})
        r = await client.get("/api/v1/dashboard/resumo")
        assert r.json()["total_cursos"] >= 1


class TestDashboardMetricas:
    async def test_metricas_retorna_lista(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.get(f"/api/v1/dashboard/metricas/{uid}")
        assert r.status_code == status.HTTP_200_OK
        assert isinstance(r.json(), list)

    async def test_metricas_limit_funciona(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.get(f"/api/v1/dashboard/metricas/{uid}?limit=5")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.json()) <= 5


class TestDashboardLogs:
    async def test_logs_retorna_lista(self, client):
        r = await client.get("/api/v1/dashboard/logs")
        assert r.status_code == status.HTTP_200_OK
        assert isinstance(r.json(), list)


class TestCursoStats:
    async def test_curso_stats_retorna_estrutura(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Stats", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.get(f"/api/v1/dashboard/cursos/{curso_id}/stats")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        chaves = {"total_inscritos", "total_concluidos", "nota_media", "taxa_conclusao"}
        assert chaves.issubset(data.keys())

    async def test_curso_stats_inexistente(self, client):
        r = await client.get("/api/v1/dashboard/cursos/99999/stats")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["total_inscritos"] == 0
