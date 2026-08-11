"""Testes reais de autenticação — usam PostgreSQL e HTTP"""

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.main import app
from app.models.log import LogAcesso
from app.services.auth import create_access_token, decode_token


class TestRegistro:
    async def test_registro_cria_solicitacao_pendente(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Novo Usuario",
                    "email": "novo@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "pendente"
        assert data["perfil_solicitado"] == "participante"

    async def test_registro_sem_aceite_lgpd_falha(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Sem LGPD",
                    "email": "semlgpd@test.com",
                    "senha": "123456",
                    "aceite_lgpd": False,
                },
            )
        assert r.status_code == 422

    async def test_registro_email_duplicado_rejeitado(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Primeiro",
                    "email": "dup@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            r = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Segundo",
                    "email": "dup@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
        assert r.status_code == 409


class TestLogin:
    async def test_login_retorna_token(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/login",
                json={
                    "email": "admin@test.com",
                    "senha": "test123",
                },
            )
        assert r.status_code == 200
        assert "access_token" in r.json()

    async def test_login_senha_invalida(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/login",
                json={
                    "email": "admin@test.com",
                    "senha": "senha_errada",
                },
            )
        assert r.status_code == 401


class TestRegistroComPerfil:
    async def test_registro_com_perfil_cria_solicitacao_pendente(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Solicitante",
                    "email": "sol@test.com",
                    "senha": "123456",
                    "perfil_solicitado": "instrutor",
                    "aceite_lgpd": True,
                },
            )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "pendente"
        assert data["perfil_solicitado"] == "instrutor"

    async def test_registro_com_perfil_invalido_falha(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Invalido",
                    "email": "inv@test.com",
                    "senha": "123456",
                    "perfil_solicitado": "admin",
                    "aceite_lgpd": True,
                },
            )
        assert r.status_code == 400


class TestLogAcesso:
    """Issue #44 — login deve gravar LogAcesso para popular as telas de log/acessos"""

    async def _buscar_logs(self):
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.config import settings

        url = settings.TEST_DATABASE_URL or settings.DATABASE_URL
        _eng = create_async_engine(url)
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        _maker = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
        session = _maker()
        try:
            result = await session.execute(select(LogAcesso).order_by(LogAcesso.criado_em.desc()))
            return result.scalars().all()
        finally:
            await session.close()
            await _eng.dispose()

    async def test_login_grava_log_de_acesso(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "senha": "test123"},
            )
        assert r.status_code == 200

        logs = await self._buscar_logs()
        assert len(logs) == 1
        assert logs[0].usuario_id == admin_user.id
        assert logs[0].acao == "login"

    async def test_login_falho_nao_grava_log(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "senha": "senha_errada"},
            )
        assert r.status_code == 401

        logs = await self._buscar_logs()
        assert len(logs) == 0

    async def test_login_grava_ip_e_dispositivo(self, db_clean, admin_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            ac.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0"})
            r = await ac.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "senha": "test123"},
            )
        assert r.status_code == 200

        logs = await self._buscar_logs()
        assert len(logs) == 1
        assert logs[0].ip_address is not None
        assert logs[0].dispositivo == "desktop"


class TestTokenJWT:
    def test_jwt_create_and_decode(self):
        uid = "550e8400-e29b-41d4-a716-446655440000"
        token = create_access_token({"sub": uid})
        payload = decode_token(token)
        assert payload["sub"] == uid
