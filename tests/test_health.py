import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "checks" in data
    assert data["checks"]["database"]["status"] == "ok"


@pytest.mark.db
class TestDeteccaoDeSchemaAtrasado:
    """Guarda o detector de schema atrasado.

    Contexto (incidente de 08/09): o deploy nao roda `alembic upgrade head` e o
    `create_all()` do startup so cria TABELA que falta, nunca COLUNA. Migration
    de coluna nao aplicada = endpoint respondendo 500 por coluna inexistente,
    sem nada gritar. Aconteceu em dev (conteudos.disponivel) e ficou ~7 dias
    silencioso em hom (presenca_aula.saida_estimada).

    Nao da pra testar "migrations reproduzem os models" neste repo: a chain
    comeca com ALTER em tabela que o create_all cria, entao ela nao constroi o
    schema do zero. O que da pra blindar e o detector -- e e o que isto faz.
    """

    async def _revisao_atual(self, session) -> str | None:
        from sqlalchemy import text

        return (await session.execute(text("SELECT version_num FROM lms.alembic_version"))).scalar_one_or_none()

    async def _gravar_revisao(self, session, revisao: str) -> None:
        from sqlalchemy import text

        await session.execute(text("UPDATE lms.alembic_version SET version_num = :r"), {"r": revisao})
        await session.commit()

    async def test_detecta_quando_o_banco_esta_atras_do_codigo(self, db_clean):
        """O caso do incidente: banco numa revisao anterior a head do codigo."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.services.health import check_migrations

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        original = await self._revisao_atual(session)
        try:
            # 'ad9d802fbf09' e a revisao em que o dev estava quando quebrou
            await self._gravar_revisao(session, "ad9d802fbf09")
            resultado = await check_migrations(session)

            assert resultado["status"] == "pendente", resultado
            assert "ad9d802fbf09" in resultado["detail"]
            assert "alembic upgrade head" in resultado["detail"], "precisa dizer o que fazer"
            # tem que listar as revisoes que faltam, nao so dizer que falta algo
            assert "c7d3e9a1f204" in resultado["detail"], resultado["detail"]
        finally:
            if original is not None:
                await self._gravar_revisao(session, original)
            await session.close()
            await engine.dispose()

    async def test_reporta_ok_quando_esta_na_head(self, db_clean):
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.services.health import check_migrations

        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        original = await self._revisao_atual(session)
        try:
            await self._gravar_revisao(session, head)
            resultado = await check_migrations(session)
            assert resultado["status"] == "ok", resultado
            assert head in resultado["detail"]
        finally:
            if original is not None:
                await self._gravar_revisao(session, original)
            await session.close()
            await engine.dispose()

    async def test_health_expoe_o_check_sem_reprovar_o_deploy(self):
        """O deploy usa /health como gate exigindo HTTP 200. Schema atrasado tem
        que aparecer no payload sem derrubar o status geral (a app sobe normal)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")

        assert response.status_code == 200
        body = response.json()
        migrations = body["checks"]["migrations"]
        assert migrations["status"] in ("ok", "pendente", "error")
        assert migrations["detail"]
        if migrations["status"] == "pendente":
            assert body["status"] == "ok", "migrations pendente nao pode degradar o status geral"


async def test_health_live():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ready():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
