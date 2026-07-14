"""Testes para Issue #21: UsuarioRead deve incluir perfis"""

import uuid

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.auth import create_access_token, decode_token


class TestPerfisNoJWT:
    """Login deve gerar token com claim perfis"""

    async def test_login_token_inclui_perfis(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "JWT Perfis",
                    "email": "jwt_perfis@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            r = await ac.post(
                "/api/v1/auth/login",
                json={"email": "jwt_perfis@test.com", "senha": "123456"},
            )
        assert r.status_code == 200
        token = r.json()["access_token"]
        payload = decode_token(token)
        assert "perfis" in payload, "Token deve conter claim 'perfis'"
        assert isinstance(payload["perfis"], list)
        assert "participante" in payload["perfis"]


class TestPerfisNoUsuarioRead:
    """Endpoints de usuario devem retornar campo perfis"""

    async def test_registro_retorna_perfis(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Reg Perfis",
                    "email": "reg_perfis@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
        assert r.status_code == 201
        data = r.json()
        assert "perfis" in data, "Resposta do registro deve conter 'perfis'"
        assert data["perfis"] == ["participante"]

    async def test_me_retorna_perfis(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Me Perfis",
                    "email": "me_perfis@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            r_login = await ac.post(
                "/api/v1/auth/login",
                json={"email": "me_perfis@test.com", "senha": "123456"},
            )
            token = r_login.json()["access_token"]
            r = await ac.get(
                "/api/v1/usuarios/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200
        data = r.json()
        assert "perfis" in data
        assert data["perfis"] == ["participante"]

    async def test_listar_usuarios_retorna_perfis(self, db_clean, admin_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(
                "/api/v1/usuarios",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "perfis" in data[0]

    async def test_obter_usuario_por_id_retorna_perfis(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            admin_id = str(admin_user.id)
            from app.services.auth import create_access_token
            token = create_access_token({"sub": admin_id, "perfis": ["administrador_geral"]})
            r = await ac.get(
                f"/api/v1/usuarios/{admin_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 200
        data = r.json()
        assert "perfis" in data
        assert "administrador_geral" in data["perfis"]


class TestPerfisNoCriarSubordinado:
    """Criar subordinado deve retornar perfis"""

    async def test_criar_subordinado_retorna_perfis(self, db_clean, admin_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/usuarios/criar-subordinado",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "nome_completo": "Subordinado Test",
                    "email": "sub@test.com",
                    "senha": "123456",
                },
            )
        assert r.status_code == 201
        data = r.json()
        assert "perfis" in data
        assert "participante" in data["perfis"]
