"""Testes para Issue #43: GET /usuarios?perfil_nome=... quebrava com AmbiguousForeignKeysError"""

from httpx import ASGITransport, AsyncClient

from app.main import app


class TestFiltroPerfil:
    """Filtrar usuarios por perfil nao deve retornar 500"""

    async def test_filtrar_por_perfil_retorna_200(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r_login = await ac.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "senha": "test123"},
            )
            assert r_login.status_code == 200
            token = r_login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = await ac.get(
                "/api/v1/usuarios?perfil_nome=administrador_geral",
                headers=headers,
            )
        assert r.status_code == 200, f"Esperado 200, veio {r.status_code}: {r.text}"

    async def test_filtrar_por_perfil_retorna_usuarios_corretos(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r_login = await ac.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "senha": "test123"},
            )
            token = r_login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = await ac.get(
                "/api/v1/usuarios?perfil_nome=administrador_geral",
                headers=headers,
            )
            data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert all("administrador_geral" in u["perfis"] for u in data)

    async def test_filtrar_perfil_sem_resultados(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r_login = await ac.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "senha": "test123"},
            )
            token = r_login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = await ac.get(
                "/api/v1/usuarios?perfil_nome=perfil_inexistente",
                headers=headers,
            )
        assert r.status_code == 200
        assert r.json() == []

    async def test_listar_sem_filtro_continua_funcionando(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r_login = await ac.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "senha": "test123"},
            )
            token = r_login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = await ac.get(
                "/api/v1/usuarios",
                headers=headers,
            )
        assert r.status_code == 200
        assert isinstance(r.json(), list)
