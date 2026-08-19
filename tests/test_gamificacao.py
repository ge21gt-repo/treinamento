import uuid

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

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
            r = await ac.post(
                "/api/v1/gamificacao/xp", json={"usuario_id": str(uuid.uuid4()), "quantidade": 100, "origem": "teste"}
            )
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
        r = await client.post(
            "/api/v1/gamificacao/xp",
            json={"usuario_id": uid, "quantidade": 200, "origem": "teste", "descricao": "XP de teste"},
        )
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

    async def test_leaderboard_aceita_periodos_validos(self, client, admin_user):
        uid = str(admin_user.id)
        await client.post("/api/v1/gamificacao/xp", json={"usuario_id": uid, "quantidade": 50, "origem": "teste"})
        for periodo in ("geral", "semanal", "mensal"):
            r = await client.get(f"/api/v1/gamificacao/leaderboard?periodo={periodo}")
            assert r.status_code == status.HTTP_200_OK
            assert isinstance(r.json(), list)

    async def test_leaderboard_periodo_invalido(self, client):
        r = await client.get("/api/v1/gamificacao/leaderboard?periodo=invalido")
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestBadges:
    async def test_create_assign_and_get_badges(self, client, admin_user):
        r = await client.post(
            "/api/v1/gamificacao/badges",
            json={
                "nome": "Primeiro Curso",
                "descricao": "Complete seu primeiro curso",
                "criterio_tipo": "cursos_concluidos",
                "criterio_valor": 1,
            },
        )
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
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Teste", "tipo": "diaria", "xp_recompensa": 500, "criterio": {"cursos": 3}},
        )
        assert r.status_code == status.HTTP_201_CREATED
        missao_id = r.json()["id"]

        r = await client.get("/api/v1/gamificacao/missoes")
        assert r.status_code == status.HTTP_200_OK
        assert any(m["id"] == missao_id for m in r.json())

    async def test_criar_missao_tipo_invalido(self, client):
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Inválida", "tipo": "mensal", "xp_recompensa": 300, "criterio": {"cursos": 3}},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_update_missao(self, client):
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Original", "tipo": "semanal", "xp_recompensa": 300, "criterio": {"xp": 1000}},
        )
        missao_id = r.json()["id"]

        r = await client.patch(f"/api/v1/gamificacao/missoes/{missao_id}", json={"titulo": "Missao Atualizada"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Missao Atualizada"

    async def test_atualizar_missao_tipo_invalido(self, client):
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Original", "tipo": "especial", "xp_recompensa": 300, "criterio": {"xp": 1000}},
        )
        missao_id = r.json()["id"]

        r = await client.patch(f"/api/v1/gamificacao/missoes/{missao_id}", json={"tipo": "mensal"})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_participar_missao(self, client, admin_user):
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Participar", "tipo": "especial", "xp_recompensa": 300, "criterio": {"xp": 1000}},
        )
        missao_id = r.json()["id"]

        uid = str(admin_user.id)
        r = await client.post(
            "/api/v1/gamificacao/missoes/participar", json={"usuario_id": uid, "missao_id": missao_id}
        )
        assert r.status_code == status.HTTP_201_CREATED
        um_id = r.json()["id"]

        r = await client.patch(
            f"/api/v1/gamificacao/missoes/usuario/{um_id}", json={"status": "concluido", "progresso_pct": 100.0}
        )
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["status"] == "concluido"

    async def test_missoes_ativas_retorna_com_status(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Ativa", "tipo": "diaria", "xp_recompensa": 100, "criterio": {"cursos": 1}},
        )
        missao_id = r.json()["id"]

        await client.post("/api/v1/gamificacao/missoes/participar", json={"usuario_id": uid, "missao_id": missao_id})

        r = await client.get("/api/v1/gamificacao/missoes/ativas")
        assert r.status_code == status.HTTP_200_OK
        ativas = r.json()
        assert isinstance(ativas, list)
        assert any(m["id"] == missao_id and m["usuario_status"] == "em_andamento" for m in ativas)

    async def test_missoes_usuario_lista_com_progresso(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Usuario", "tipo": "semanal", "xp_recompensa": 200, "criterio": {"xp": 500}},
        )
        missao_id = r.json()["id"]

        await client.post("/api/v1/gamificacao/missoes/participar", json={"usuario_id": uid, "missao_id": missao_id})

        r = await client.get(f"/api/v1/gamificacao/missoes/usuario/{uid}")
        assert r.status_code == status.HTTP_200_OK
        lista = r.json()
        assert isinstance(lista, list)
        assert any(
            m["id"] == missao_id and m["usuario_status"] == "em_andamento" and "usuario_progresso_pct" in m
            for m in lista
        )


class TestStreaks:
    async def test_get_streak_inexistente(self, client):
        r = await client.get("/api/v1/gamificacao/streaks/00000000-0000-0000-0000-000000009999")
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestPerfil:
    async def test_perfil_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/gamificacao/perfil")
        assert r.status_code in AUTH_OK

    async def test_perfil_retorna_campos_completos(self, client):
        r = await client.get("/api/v1/gamificacao/perfil")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert "usuario_id" in data
        assert "nome_completo" in data
        assert isinstance(data["xp_total"], int)
        assert "nivel_atual" in data
        assert "nome" in data["nivel_atual"]
        assert "ordem" in data["nivel_atual"]
        assert "xp_minimo" in data["nivel_atual"]
        assert isinstance(data["badges"], list)
        assert "streak" in data
        assert "dias_consecutivos" in data["streak"]
        assert "maior_streak" in data["streak"]
        assert isinstance(data["historico_recente"], list)

    async def test_perfil_reflete_dados_corretos(self, client, admin_user):
        uid = str(admin_user.id)

        r = await client.post(
            "/api/v1/gamificacao/xp",
            json={"usuario_id": uid, "quantidade": 200, "origem": "teste", "descricao": "XP teste perfil"},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.post(
            "/api/v1/gamificacao/badges",
            json={"nome": "BadgePerfil", "descricao": "Badge de teste", "criterio_tipo": "xp_acumulado", "criterio_valor": 1},
        )
        assert r.status_code == status.HTTP_201_CREATED
        badge_id = r.json()["id"]

        r = await client.post("/api/v1/gamificacao/badges/atribuir", json={"usuario_id": uid, "badge_id": badge_id})
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get("/api/v1/gamificacao/perfil")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["xp_total"] >= 200
        assert any(b["id"] == badge_id for b in data["badges"])
        assert len(data["historico_recente"]) >= 1
        assert data["historico_recente"][0]["quantidade"] == 200


class TestRetroativoBadge:
    """Issue 21 — badge concedida retroativamente (nao so no proximo XP)"""

    async def test_badge_nova_concedida_a_quem_ja_cumpre(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.post(
            "/api/v1/gamificacao/xp",
            json={"usuario_id": uid, "quantidade": 300, "origem": "teste", "descricao": "XP retro"},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.post(
            "/api/v1/gamificacao/badges",
            json={"nome": "BadgeRetro", "descricao": "x", "criterio_tipo": "xp_acumulado", "criterio_valor": 100},
        )
        assert r.status_code == status.HTTP_201_CREATED
        badge_id = r.json()["id"]

        r = await client.get("/api/v1/gamificacao/perfil")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert any(b["id"] == badge_id for b in data["badges"]), (
            "Badge nova deveria ter sido concedida retroativamente ao olhar o perfil"
        )


class TestMissoesDuplicidade:
    """Issue 22 — participar missao idempotente + lista de participantes"""

    async def test_participar_duas_vezes_nao_duplica(self, client, admin_user):
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Dupla", "tipo": "diaria", "xp_recompensa": 100, "criterio": {"cursos": 1}},
        )
        missao_id = r.json()["id"]
        uid = str(admin_user.id)
        payload = {"usuario_id": uid, "missao_id": missao_id}

        r1 = await client.post("/api/v1/gamificacao/missoes/participar", json=payload)
        assert r1.status_code == status.HTTP_201_CREATED
        r2 = await client.post("/api/v1/gamificacao/missoes/participar", json=payload)
        assert r2.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
        assert r2.json()["id"] == r1.json()["id"], "Participar 2x nao deve criar duplicata"

        r = await client.get(f"/api/v1/gamificacao/missoes/{missao_id}/participantes")
        assert r.status_code == status.HTTP_200_OK
        assert sum(1 for p in r.json() if p["usuario_id"] == uid) == 1, "Deve haver 1 linha de participacao"

    async def test_aluno_ve_proprio_historico(self, client, admin_user):
        r = await client.post(
            "/api/v1/gamificacao/missoes",
            json={"titulo": "Missao Hist", "tipo": "semanal", "xp_recompensa": 200, "criterio": {"cursos": 1}},
        )
        missao_id = r.json()["id"]
        uid = str(admin_user.id)
        await client.post("/api/v1/gamificacao/missoes/participar", json={"usuario_id": uid, "missao_id": missao_id})

        r = await client.get(f"/api/v1/gamificacao/missoes/usuario/{uid}")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert any(m["id"] == missao_id for m in r.json()), "Proprio usuario deve ver o proprio historico"


class TestGestaoBadges:
    """Issue 18 — gestao de badges: listar inativas e contar conquistas"""

    async def test_listagem_padrao_somente_ativas(self, client):
        r = await client.post(
            "/api/v1/gamificacao/badges",
            json={"nome": "BadgeGestaoA", "descricao": "x", "criterio_tipo": "xp_acumulado", "criterio_valor": 10},
        )
        badge_id = r.json()["id"]
        r = await client.patch(f"/api/v1/gamificacao/badges/{badge_id}", json={"ativo": False})
        assert r.status_code == status.HTTP_200_OK

        r = await client.get("/api/v1/gamificacao/badges")
        assert r.status_code == status.HTTP_200_OK
        assert not any(b["id"] == badge_id for b in r.json()), "Listagem padrao nao deve incluir inativa"

    async def test_incluir_inativas_lista_e_conta_conquistas(self, client, admin_user):
        r = await client.post(
            "/api/v1/gamificacao/badges",
            json={"nome": "BadgeGestaoB", "descricao": "x", "criterio_tipo": "xp_acumulado", "criterio_valor": 10},
        )
        assert r.status_code == status.HTTP_201_CREATED
        badge_id = r.json()["id"]
        uid = str(admin_user.id)
        r = await client.post("/api/v1/gamificacao/badges/atribuir", json={"usuario_id": uid, "badge_id": badge_id})
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get("/api/v1/gamificacao/badges")
        assert r.status_code == status.HTTP_200_OK
        badge = next((b for b in r.json() if b["id"] == badge_id), None)
        assert badge is not None
        assert badge["conquistas"] == 1, f"Esperava 1 conquista, veio {badge.get('conquistas')}"

        r = await client.patch(f"/api/v1/gamificacao/badges/{badge_id}", json={"ativo": False})
        assert r.status_code == status.HTTP_200_OK

        r = await client.get("/api/v1/gamificacao/badges?incluir_inativas=true")
        assert r.status_code == status.HTTP_200_OK
        badge = next((b for b in r.json() if b["id"] == badge_id), None)
        assert badge is not None, "incluir_inativas=true deve trazer a badge desativada"
        assert badge["conquistas"] == 1
