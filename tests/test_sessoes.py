import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import status

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


async def criar_curso(client, titulo="Curso Teste"):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
    return r.json()["id"]


class TestSessoesAuth:
    async def test_list_sessoes_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/sessoes")
        assert r.status_code in AUTH_OK

    async def test_create_sessao_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/sessoes", json={"titulo": "x", "instrutor_id": "00000000-0000-0000-0000-000000000001", "data_hora_inicio": "2026-07-14T10:00:00Z"})
        assert r.status_code in AUTH_OK


class TestSessoesCRUD:
    async def test_create_and_get_sessao(self, client, admin_user):
        curso_id = await criar_curso(client, "Curso Sessao")
        uid = str(admin_user.id)
        r = await client.post("/api/v1/sessoes", json={
            "curso_id": curso_id,
            "titulo": "Live de Python",
            "instrutor_id": uid,
            "data_hora_inicio": "2026-07-14T10:00:00Z",
            "descricao": "Sessao ao vivo sobre Python",
            "max_participantes": 50,
        })
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["titulo"] == "Live de Python"
        sessao_id = data["id"]

        r = await client.get(f"/api/v1/sessoes/{sessao_id}")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Live de Python"

    async def test_update_sessao(self, client, admin_user):
        curso_id = await criar_curso(client, "Curso Update")
        uid = str(admin_user.id)
        r = await client.post("/api/v1/sessoes", json={
            "titulo": "Original", "instrutor_id": uid,
            "data_hora_inicio": "2026-07-14T10:00:00Z",
        })
        sessao_id = r.json()["id"]

        r = await client.patch(f"/api/v1/sessoes/{sessao_id}", json={"titulo": "Atualizada"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Atualizada"

    async def test_delete_sessao(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.post("/api/v1/sessoes", json={
            "titulo": "Pra Deletar", "instrutor_id": uid,
            "data_hora_inicio": "2026-07-14T10:00:00Z",
        })
        sessao_id = r.json()["id"]

        r = await client.delete(f"/api/v1/sessoes/{sessao_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

        r = await client.get(f"/api/v1/sessoes/{sessao_id}")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_list_sessoes_filter(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.get("/api/v1/sessoes")
        assert r.status_code == status.HTTP_200_OK
        assert isinstance(r.json(), list)


class TestPresenca:
    async def test_register_and_get_presenca(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.post("/api/v1/sessoes", json={
            "titulo": "Sessao Presenca", "instrutor_id": uid,
            "data_hora_inicio": "2026-07-14T10:00:00Z",
        })
        sessao_id = r.json()["id"]

        r = await client.post("/api/v1/sessoes/presenca", json={
            "sessao_id": sessao_id,
            "usuario_id": uid,
            "hora_entrada": "2026-07-14T10:00:00Z",
        })
        assert r.status_code == status.HTTP_201_CREATED
        presenca_id = r.json()["id"]

        r = await client.get(f"/api/v1/sessoes/presenca/{sessao_id}")
        assert r.status_code == status.HTTP_200_OK
        presencas = r.json()
        assert len(presencas) >= 1

        r = await client.patch(f"/api/v1/sessoes/presenca/{presenca_id}", json={"presente": False})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["presente"] is False
