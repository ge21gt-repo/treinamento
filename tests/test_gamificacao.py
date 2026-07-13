import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import status

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class TestGamificacaoAuth:
    async def test_list_niveis_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/gamificacao/niveis")
        assert r.status_code in AUTH_OK

    async def test_create_xp_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/gamificacao/xp", json={"usuario_id": str(uuid.uuid4()), "quantidade": 100, "origem": "teste"})
        assert r.status_code in AUTH_OK

    async def test_leaderboard_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/gamificacao/leaderboard")
        assert r.status_code in AUTH_OK


class TestNiveis:
    async def test_create_and_list_niveis(self, client):
        r = await client.post("/api/v1/gamificacao/niveis", json={"nome": "Expert", "xp_minimo": 5000, "ordem": 10})
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["nome"] == "Expert"

        r = await client.get("/api/v1/gamificacao/niveis")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert any(n["nome"] == "Expert" for n in data)


class TestXP:
    async def test_add_and_get_xp(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.post("/api/v1/gamificacao/xp", json={"usuario_id": uid, "quantidade": 200, "origem": "teste", "descricao": "XP de teste"})
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["quantidade"] == 200

        r = await client.get(f"/api/v1/gamificacao/xp/{uid}")
        assert r.status_code == status.HTTP_200_OK
        records = r.json()
        assert len(records) >= 1

    async def test_xp_total_and_level(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.get(f"/api/v1/gamificacao/xp/{uid}/total")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert "xp_total" in data
        assert "nivel" in data

    async def test_leaderboard(self, client, admin_user):
        uid = str(admin_user.id)
        await client.post("/api/v1/gamificacao/xp", json={"usuario_id": uid, "quantidade": 50, "origem": "teste"})
        r = await client.get("/api/v1/gamificacao/leaderboard?limit=10")
        assert r.status_code == status.HTTP_200_OK
        board = r.json()
        assert isinstance(board, list)
        if board:
            assert "usuario_id" in board[0]


class TestBadges:
    async def test_create_assign_and_get_badges(self, client, admin_user):
        r = await client.post("/api/v1/gamificacao/badges", json={"nome": "Primeiro Curso", "descricao": "Complete seu primeiro curso", "criterio_tipo": "cursos_concluidos", "criterio_valor": 1})
        assert r.status_code == status.HTTP_201_CREATED
        badge_id = r.json()["id"]

        r = await client.get("/api/v1/gamificacao/badges")
        assert r.status_code == status.HTTP_200_OK
        assert any(b["nome"] == "Primeiro Curso" for b in r.json())

        uid = str(admin_user.id)
        r = await client.post("/api/v1/gamificacao/badges/atribuir", json={"usuario_id": uid, "badge_id": badge_id})
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/gamificacao/badges/{uid}")
        assert r.status_code == status.HTTP_200_OK
        user_badges = r.json()
        assert any(b["badge_id"] == badge_id for b in user_badges)


class TestMissoes:
    async def test_create_missao(self, client):
        r = await client.post("/api/v1/gamificacao/missoes", json={"titulo": "Missao Teste", "tipo": "cursos", "xp_recompensa": 500, "criterio": {"cursos": 3}})
        assert r.status_code == status.HTTP_201_CREATED
        missao_id = r.json()["id"]

        r = await client.get("/api/v1/gamificacao/missoes")
        assert r.status_code == status.HTTP_200_OK
        assert any(m["id"] == missao_id for m in r.json())

    async def test_update_missao(self, client):
        r = await client.post("/api/v1/gamificacao/missoes", json={"titulo": "Missao Original", "tipo": "xp", "xp_recompensa": 300, "criterio": {"xp": 1000}})
        missao_id = r.json()["id"]

        r = await client.patch(f"/api/v1/gamificacao/missoes/{missao_id}", json={"titulo": "Missao Atualizada"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Missao Atualizada"

    async def test_participar_missao(self, client, admin_user):
        r = await client.post("/api/v1/gamificacao/missoes", json={"titulo": "Missao Participar", "tipo": "xp", "xp_recompensa": 300, "criterio": {"xp": 1000}})
        missao_id = r.json()["id"]

        uid = str(admin_user.id)
        r = await client.post("/api/v1/gamificacao/missoes/participar", json={"usuario_id": uid, "missao_id": missao_id})
        assert r.status_code == status.HTTP_201_CREATED
        um_id = r.json()["id"]

        r = await client.patch(f"/api/v1/gamificacao/missoes/usuario/{um_id}", json={"status": "concluido", "progresso_pct": 100.0})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["status"] == "concluido"


class TestStreaks:
    async def test_get_streak_inexistente(self, client):
        r = await client.get("/api/v1/gamificacao/streaks/00000000-0000-0000-0000-000000009999")
        assert r.status_code == status.HTTP_404_NOT_FOUND
