"""Testes para Issue #23: unique constraint no telefone"""

from httpx import ASGITransport, AsyncClient

from app.main import app


class TestTelefoneDuplicado:
    async def test_registro_telefone_duplicado_retorna_409(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Tel A",
                    "email": "tela@test.com",
                    "telefone": "11988887777",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Tel B",
                    "email": "telb@test.com",
                    "telefone": "11988887777",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
        assert r2.status_code == 409

    async def test_registro_com_perfil_telefone_duplicado_retorna_409(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Tel C",
                    "email": "telc@test.com",
                    "telefone": "11988886666",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/auth/registro-com-perfil",
                json={
                    "nome_completo": "Tel D",
                    "email": "teld@test.com",
                    "telefone": "11988886666",
                    "senha": "123456",
                    "perfil_solicitado": "instrutor",
                    "aceite_lgpd": True,
                },
            )
        assert r2.status_code == 409

    async def test_criar_subordinado_telefone_duplicado_retorna_409(self, db_clean, admin_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Tel E",
                    "email": "tele@test.com",
                    "telefone": "11988885555",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/usuarios/criar-subordinado",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "nome_completo": "Tel F",
                    "email": "telf@test.com",
                    "telefone": "11988885555",
                    "senha": "123456",
                },
            )
        assert r2.status_code == 409

    async def test_migration_005_telefone_unique_existe(self):
        from alembic.script import ScriptDirectory
        from alembic.config import Config

        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        assert "005_add_telefone_unique_constraint" in heads, (
            f"Migration 005 deve estar entre os heads. Heads atuais: {heads}"
        )

    async def test_modelo_telefone_unique_true(self):
        from app.models.usuario import Usuario

        assert Usuario.__table__.c.telefone.unique is True
