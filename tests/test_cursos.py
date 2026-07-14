import pytest

pytestmark = pytest.mark.db


async def criar_curso(client, titulo="Curso Teste", trilha_id=None):
    payload = {
        "titulo": titulo,
        "descricao": "Descricao do curso",
        "ordem": 0,
        "publicado": True,
    }
    if trilha_id is not None:
        payload["trilha_id"] = trilha_id
    response = await client.post("/api/v1/cursos", json=payload)
    return response


class TestCursosCRUD:
    async def test_criar_curso(self, client):
        response = await criar_curso(client, "Curso Novo")
        assert response.status_code == 201
        data = response.json()
        assert data["titulo"] == "Curso Novo"
        assert "id" in data

    async def test_listar_cursos(self, client):
        await criar_curso(client, "Curso A")
        await criar_curso(client, "Curso B")
        response = await client.get("/api/v1/cursos")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

    async def test_obter_curso(self, client):
        criar_resp = await criar_curso(client, "Curso Unico")
        curso_id = criar_resp.json()["id"]
        response = await client.get(f"/api/v1/cursos/{curso_id}")
        assert response.status_code == 200

    async def test_atualizar_curso(self, client):
        criar_resp = await criar_curso(client, "Curso Original")
        curso_id = criar_resp.json()["id"]
        response = await client.patch(
            f"/api/v1/cursos/{curso_id}",
            json={"titulo": "Curso Atualizado"},
        )
        assert response.status_code == 200
        assert response.json()["titulo"] == "Curso Atualizado"

    async def test_excluir_curso(self, client):
        criar_resp = await criar_curso(client, "Curso Deletar")
        curso_id = criar_resp.json()["id"]
        response = await client.delete(f"/api/v1/cursos/{curso_id}")
        assert response.status_code == 204


class TestFiltroTrilha:
    async def test_filtrar_cursos_por_trilha(self, client):
        trilha_resp = await client.post(
            "/api/v1/trilhas",
            json={
                "titulo": "Trilha Cursos",
                "nivel": "iniciante",
            },
        )
        trilha_id = trilha_resp.json()["id"]

        await criar_curso(client, "Curso Trilha 1", trilha_id=trilha_id)
        await criar_curso(client, "Curso Trilha 2", trilha_id=trilha_id)
        await criar_curso(client, "Curso Solto")

        response = await client.get(f"/api/v1/cursos?trilha_id={trilha_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(c["trilha_id"] == trilha_id for c in data)

    async def test_filtrar_trilha_sem_cursos(self, client):
        response = await client.get("/api/v1/cursos?trilha_id=99999")
        assert response.status_code == 200
        assert response.json() == []

    async def test_filtrar_trilha_invalida(self, client):
        response = await client.get("/api/v1/cursos?trilha_id=abc")
        assert response.status_code == 422
