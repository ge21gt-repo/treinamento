import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


class TestBootAplicacao:
    """Valida que o start da app (lifespan: create_all + seeds) nao crasha.

    Previne incidentes como o de 14/08, onde um seed com coluna NOT NULL
    faltando derrubava hom/dev com 502 no health check.
    """

    async def test_lifespan_inicia_sem_crash(self, db_clean):
        from app.main import app, lifespan

        async with lifespan(app):
            assert True

    async def test_seed_niveis_esta_consistente(self, db_clean):
        from app.main import app, lifespan
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings

        async with lifespan(app):
            engine = create_async_engine(settings.TEST_DATABASE_URL)
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            session = maker()
            try:
                niveis = (
                    await session.execute(
                        text("SELECT nome, xp_minimo, ordem FROM lms.niveis ORDER BY ordem")
                    )
                ).all()
                nomes = [n.nome for n in niveis]
                assert nomes == ["Iniciante", "Bronze", "Prata", "Ouro", "Platina", "Diamante", "Mestre"]
                assert [n.ordem for n in niveis] == [1, 2, 3, 4, 5, 6, 7]
                assert niveis[-1].xp_minimo == 20000  # Mestre
            finally:
                await session.close()
                await engine.dispose()

    async def test_seed_badges_tem_todas_colunas_not_null(self, db_clean):
        from app.main import app, lifespan
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings

        async with lifespan(app):
            engine = create_async_engine(settings.TEST_DATABASE_URL)
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            session = maker()
            try:
                badges = (
                    await session.execute(text("SELECT nome, criterio_tipo, criterio_valor, ativo FROM lms.badges"))
                ).all()
                assert len(badges) >= 1
                for b in badges:
                    assert b.ativo is not None  # coluna NOT NULL preenchida pelo seed
            finally:
                await session.close()
                await engine.dispose()
