"""Tests for the gamification XP engine.

Each test creates its own engine + session to avoid asyncpg event-loop issues
with shared pools across fixtures.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.gamificacao import PontosXP
from app.models.usuario import Usuario, UsuarioPerfil
from app.services.auth import hash_password
from app.services.gamificacao import atribuir_xp

pytestmark = pytest.mark.db

_DB_URL = settings.TEST_DATABASE_URL or settings.DATABASE_URL


@pytest.fixture(scope="module")
def db_url():
    return _DB_URL


class TestEngine:
    async def _run_with_session(self, db_url, callback):
        eng = create_async_engine(db_url)
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker.begin() as session:
            for tbl in ["lms.pontos_xp", "lms.usuario_perfil", "lms.usuarios"]:
                await session.execute(text(f"TRUNCATE {tbl} CASCADE"))
            uid = uuid.uuid4()
            session.add(Usuario(
                id=uid, nome_completo="Admin",
                email=f"admin_{uid.hex[:8]}@test.com",
                senha_hash=hash_password("test123"),
                ativo=True, status_credenciamento="aprovado", aceite_lgpd=True,
            ))
            await session.flush()
            pid = await session.scalar(text("SELECT id FROM lms.perfis WHERE nome = 'administrador_geral'"))
            session.add(UsuarioPerfil(usuario_id=uid, perfil_id=pid))
            await callback(session, uid)
        await eng.dispose()

    async def test_atribuir_xp_valido(self, db_url):
        async def check(session, uid):
            pts = await atribuir_xp(session, usuario_id=uid, evento="unidade_concluida", referencia_id=1, descricao="Modulo 1")
            assert pts is not None
            assert pts.quantidade == 50
            assert pts.origem == "unidade_concluida"
            total = await session.scalar(
                select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(PontosXP.usuario_id == uid)
            )
            assert total == 50
        await self._run_with_session(db_url, check)

    async def test_atribuir_xp_idempotente(self, db_url):
        async def check(session, uid):
            pts1 = await atribuir_xp(session, usuario_id=uid, evento="unidade_concluida", referencia_id=1)
            assert pts1 is not None
            pts2 = await atribuir_xp(session, usuario_id=uid, evento="unidade_concluida", referencia_id=1)
            assert pts2 is None
            qtd = await session.scalar(select(func.count(PontosXP.id)).where(PontosXP.usuario_id == uid))
            assert qtd == 1
        await self._run_with_session(db_url, check)

    async def test_atribuir_xp_evento_invalido(self, db_url):
        async def check(session, uid):
            with pytest.raises(ValueError, match="Evento desconhecido"):
                await atribuir_xp(session, usuario_id=uid, evento="evento_inexistente")
        await self._run_with_session(db_url, check)
