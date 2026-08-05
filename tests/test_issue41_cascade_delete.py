import pytest
from fastapi import status

pytestmark = pytest.mark.db


async def _criar_curso(client, titulo="Curso Cascade"):
    r = await client.post(
        "/api/v1/cursos",
        json={"titulo": titulo, "descricao": "desc", "ordem": 0, "publicado": True},
    )
    return r.json()["id"]


async def _criar_modulo(client, curso_id, titulo="Modulo Cascade"):
    r = await client.post(
        "/api/v1/cursos/modulos",
        json={"curso_id": curso_id, "titulo": titulo, "descricao": "desc", "ordem": 0},
    )
    return r.json()["id"]


async def _criar_unidade(client, modulo_id, titulo="Unidade Cascade"):
    r = await client.post(
        "/api/v1/cursos/unidades",
        json={
            "modulo_id": modulo_id,
            "titulo": titulo,
            "tipo": "conteudo",
            "descricao": "desc",
            "conteudo_url": "https://exemplo.com/aula.pdf",
            "ordem": 0,
        },
    )
    return r.json()["id"]


class TestIssue41CascadeDelete:
    """Deletar unidade/modulo/curso/trilha com progresso ou inscricoes nao deve lancar IntegrityError"""

    async def test_excluir_unidade_com_progresso(self, client):
        curso_id = await _criar_curso(client)
        modulo_id = await _criar_modulo(client, curso_id)
        unidade_id = await _criar_unidade(client, modulo_id)

        await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        r_prog = await client.post(f"/api/v1/cursos/unidades/{unidade_id}/concluir")
        assert r_prog.status_code == status.HTTP_200_OK

        r = await client.delete(f"/api/v1/cursos/unidades/{unidade_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

    async def test_excluir_modulo_com_progresso(self, client):
        curso_id = await _criar_curso(client)
        modulo_id = await _criar_modulo(client, curso_id)
        unidade_id = await _criar_unidade(client, modulo_id)

        await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        r_prog = await client.post(f"/api/v1/cursos/unidades/{unidade_id}/concluir")
        assert r_prog.status_code == status.HTTP_200_OK

        r = await client.delete(f"/api/v1/cursos/modulos/{modulo_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

    async def test_excluir_curso_com_inscricao(self, client):
        curso_id = await _criar_curso(client)
        r_insc = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r_insc.status_code == status.HTTP_201_CREATED

        r = await client.delete(f"/api/v1/cursos/{curso_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

    async def test_excluir_trilha_com_inscricao(self, client):
        r_trilha = await client.post(
            "/api/v1/trilhas",
            json={"titulo": "Trilha Cascade", "descricao": "desc", "nivel": "iniciante", "publicada": True},
        )
        trilha_id = r_trilha.json()["id"]
        r_insc = await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")
        assert r_insc.status_code == status.HTTP_201_CREATED

        r = await client.delete(f"/api/v1/trilhas/{trilha_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT
