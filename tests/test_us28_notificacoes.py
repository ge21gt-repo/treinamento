"""Testes issue 28: notificacoes (aviso de aula + rotas da plataforma)."""

from fastapi import status

pytestmark = __import__("pytest").mark.db


async def _setup_curso_inscrito(client):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Notificacao", "descricao": "x", "ordem": 0, "publicado": True})
    curso_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return curso_id


class TestRotasNotificacoes:
    """Issue 28 — rotas minimas do sino"""

    async def test_listar_vazia(self, client):
        r = await client.get("/api/v1/notificacoes")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert data["total"] == 0
        assert data["nao_lidas"] == 0
        assert data["itens"] == []

    async def test_aula_agendada_notifica_inscritos(self, client):
        curso_id = await _setup_curso_inscrito(client)
        r = await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={"curso_id": curso_id, "titulo": "Aula Aviso", "data_hora": "2099-01-01T10:00:00Z", "duracao_minutos": 60},
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text

        r = await client.get("/api/v1/notificacoes")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert data["total"] >= 1, "Inscrito deve receber notificacao de aula agendada"
        assert data["nao_lidas"] >= 1
        assert data["itens"][0]["tipo"] == "aula_agendada"
        assert data["itens"][0]["referencia_tipo"] == "aula"

    async def test_marcar_lida(self, client):
        curso_id = await _setup_curso_inscrito(client)
        await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={"curso_id": curso_id, "titulo": "Aula Lida", "data_hora": "2099-01-02T10:00:00Z", "duracao_minutos": 60},
        )
        r = await client.get("/api/v1/notificacoes")
        notif_id = r.json()["itens"][0]["id"]

        r = await client.patch(f"/api/v1/notificacoes/{notif_id}/lida")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["lida"] is True

        r = await client.get("/api/v1/notificacoes")
        assert r.json()["nao_lidas"] == 0

    async def test_marcar_todas_lidas(self, client):
        curso_id = await _setup_curso_inscrito(client)
        await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={"curso_id": curso_id, "titulo": "Aula Todas", "data_hora": "2099-01-03T10:00:00Z", "duracao_minutos": 60},
        )
        r = await client.post("/api/v1/notificacoes/marcar-todas-lidas")
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get("/api/v1/notificacoes")
        assert r.json()["nao_lidas"] == 0