"""Testes US-11 — sessões ao vivo (código de acesso, acesso, presença)"""

from datetime import datetime, timedelta, timezone

from fastapi import status

from app.main import app
from app.services.auth import create_access_token


async def criar_curso(client, titulo="Curso US11"):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0, "publicado": True})
    return r.json()["id"]


async def criar_aula(client, curso_id, **kwargs):
    payload = {
        "curso_id": curso_id,
        "titulo": "Aula ao vivo",
        "data_hora": "2026-09-01T14:00:00Z",
        "duracao_minutos": 60,
        "link_externo": "https://teams.example.com/meeting",
    }
    payload.update(kwargs)
    r = await client.post(f"/api/v1/cursos/{curso_id}/aulas", json=payload)
    return r


class TestCodigoAcesso:
    """T-11.1 — CRUD de sessão ao vivo com código de acesso"""

    async def test_criar_aula_gera_codigo_automaticamente(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(client, curso_id)
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["codigo_acesso"]
        assert len(data["codigo_acesso"]) == 8
        assert data["data_hora_fim"] is not None

    async def test_criar_aula_com_codigo_informado(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(client, curso_id, codigo_acesso="ABC-1234")
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["codigo_acesso"] == "ABC-1234"

    async def test_criar_aula_data_fim_menor_que_inicio_falha(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(
            client,
            curso_id,
            data_hora="2026-09-01T14:00:00Z",
            data_hora_fim="2026-09-01T13:00:00Z",
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_atualizar_aula_recalcula_data_fim(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(client, curso_id)
        aula_id = r.json()["id"]
        r = await client.patch(f"/api/v1/cursos/aulas/{aula_id}", json={"duracao_minutos": 120})
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        inicio = datetime.fromisoformat(data["data_hora"].replace("Z", "+00:00"))
        fim = datetime.fromisoformat(data["data_hora_fim"].replace("Z", "+00:00"))
        assert fim - inicio == timedelta(minutes=120)

    async def test_atualizar_aula_data_fim_invalida_falha(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(client, curso_id)
        aula_id = r.json()["id"]
        r = await client.patch(
            f"/api/v1/cursos/aulas/{aula_id}",
            json={"data_hora": "2026-09-01T14:00:00Z", "data_hora_fim": "2026-09-01T13:00:00Z"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestAcessarAula:
    """T-11.5 — participante acessa a sessão ao vivo"""

    async def test_acessar_aula_com_codigo_correto(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(client, curso_id, codigo_acesso="ABC-1234")
        aula_id = r.json()["id"]
        await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})

        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/acessar", json={"codigo_acesso": "ABC-1234"})
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["link_externo"] == "https://teams.example.com/meeting"

    async def test_acessar_aula_com_codigo_errado(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(client, curso_id, codigo_acesso="ABC-1234")
        aula_id = r.json()["id"]

        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/acessar", json={"codigo_acesso": "ERRO-999"})
        assert r.status_code == status.HTTP_403_FORBIDDEN

    async def test_acessar_aula_inexistente(self, client):
        r = await client.post("/api/v1/cursos/aulas/999999/acessar", json={"codigo_acesso": "ABC-1234"})
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestPresenca:
    """T-11.3 — entrada e saída de participantes"""

    async def test_entrar_e_sair_registra_presenca(self, client):
        curso_id = await criar_curso(client)
        r = await criar_aula(client, curso_id, codigo_acesso="ABC-1234")
        aula_id = r.json()["id"]

        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code == status.HTTP_201_CREATED
        presenca_id = r.json()["id"]
        assert r.json()["hora_entrada"] is not None

        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/sair")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["id"] == presenca_id
        assert r.json()["hora_saida"] is not None
        assert r.json()["tempo_permanencia_seg"] >= 0
