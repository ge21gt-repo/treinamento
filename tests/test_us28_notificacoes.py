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

    async def test_notificacao_aula_usa_horario_local_nao_utc(self, client):
        """Issue 40: corpo mostra o horario de Sao Paulo (UTC-3), nao o UTC cru."""
        curso_id = await _setup_curso_inscrito(client)
        r = await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={
                "curso_id": curso_id,
                "titulo": "Aula Fuso",
                "data_hora": "2026-09-15T17:00:00Z",
                "duracao_minutos": 60,
            },
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text

        r = await client.get("/api/v1/notificacoes")
        notif = next(n for n in r.json()["itens"] if n["titulo"] == "Aula agendada: Aula Fuso")
        assert "14:00" in notif["corpo"], notif["corpo"]
        assert "17:00" not in notif["corpo"]


class TestNotificacaoPorEmail:
    """Issue 42 — notificacao tambem sai por e-mail, sem bloquear a resposta."""

    async def test_aula_agendada_dispara_email_em_background(self, client, monkeypatch):
        chamadas = []

        def _fake_send(destino_email, titulo, corpo):
            chamadas.append((destino_email, titulo, corpo))
            return True

        monkeypatch.setattr("app.services.notificacoes.send_notificacao_email", _fake_send)

        curso_id = await _setup_curso_inscrito(client)
        r = await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={
                "curso_id": curso_id,
                "titulo": "Aula Email",
                "data_hora": "2099-01-04T10:00:00Z",
                "duracao_minutos": 60,
            },
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text

        assert len(chamadas) >= 1, "aula_agendada deveria disparar e-mail"
        assert chamadas[0][1] == "Aula agendada: Aula Email"

    async def test_tipo_fora_da_lista_nao_dispara_email(self, client, monkeypatch):
        """'badge_conquistada' nao esta em TIPOS_QUE_VAO_POR_EMAIL -- nao deveria agendar nada."""
        chamadas = []
        monkeypatch.setattr(
            "app.services.notificacoes.send_notificacao_email",
            lambda *a, **k: chamadas.append(a) or True,
        )

        from fastapi import BackgroundTasks

        from app.database import async_session
        from app.services.notificacoes import notificar_inscritos

        curso_id = await _setup_curso_inscrito(client)
        background_tasks = BackgroundTasks()
        async with async_session() as db:
            await notificar_inscritos(
                db,
                curso_id=curso_id,
                tipo="badge_conquistada",
                titulo="Nova badge!",
                background_tasks=background_tasks,
            )
            await db.commit()
        await background_tasks()

        assert chamadas == []
