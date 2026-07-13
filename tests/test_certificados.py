import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import status

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


async def criar_curso(client, titulo="Curso Teste"):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
    return r.json()["id"]


class TestCertificadosAuth:
    async def test_list_modelos_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/certificados/modelos")
        assert r.status_code in AUTH_OK

    async def test_emitir_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/certificados", json={"usuario_id": "00000000-0000-0000-0000-000000000001", "curso_id": 1, "carga_horaria": 40})
        assert r.status_code in AUTH_OK

    async def test_validar_publico(self, client):
        """GET /certificados/validar/{hash} é público (sem auth)"""
        r = await client.get("/api/v1/certificados/validar/hash_invalido_xyz")
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestModelos:
    async def test_create_and_list_modelos(self, client):
        r = await client.post("/api/v1/certificados/modelos", json={
            "nome": "Modelo Padrao",
            "template_html": "<h1>Certificado</h1><p>{{nome}}</p>",
        })
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["nome"] == "Modelo Padrao"

        r = await client.get("/api/v1/certificados/modelos")
        assert r.status_code == status.HTTP_200_OK
        modelos = r.json()
        assert any(m["nome"] == "Modelo Padrao" for m in modelos)


class TestCertificados:
    async def test_emitir_and_get_certificado(self, client, admin_user):
        curso_id = await criar_curso(client, "Curso Certificado")
        uid = str(admin_user.id)

        r = await client.post("/api/v1/certificados/modelos", json={
            "nome": "Modelo Curso",
            "template_html": "<p>Certificado</p>",
        })
        modelo_id = r.json()["id"]

        r = await client.post("/api/v1/certificados", json={
            "usuario_id": uid,
            "curso_id": curso_id,
            "modelo_id": modelo_id,
            "carga_horaria": 40,
            "nota_final": 85.0,
        })
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert "hash_validacao" in data
        assert data["carga_horaria"] == 40
        cert_id = data["id"]

        r = await client.get(f"/api/v1/certificados/{cert_id}")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["id"] == cert_id

        r = await client.get(f"/api/v1/certificados/usuario/{uid}")
        assert r.status_code == status.HTTP_200_OK
        certs = r.json()
        assert any(c["id"] == cert_id for c in certs)

    async def test_validar_por_hash(self, client, admin_user):
        curso_id = await criar_curso(client, "Curso Validacao")
        uid = str(admin_user.id)
        r = await client.post("/api/v1/certificados", json={
            "usuario_id": uid,
            "curso_id": curso_id,
            "carga_horaria": 20,
        })
        hash_val = r.json()["hash_validacao"]

        r = await client.get(f"/api/v1/certificados/validar/{hash_val}")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["hash_validacao"] == hash_val

    async def test_validar_hash_invalido(self, client):
        r = await client.get("/api/v1/certificados/validar/hash_inexistente_12345")
        assert r.status_code == status.HTTP_404_NOT_FOUND
