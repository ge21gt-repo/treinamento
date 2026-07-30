"""Tests for the gamification XP engine.

Each test creates its own engine + session to avoid asyncpg event-loop issues
with shared pools across fixtures.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.curso import Curso, Inscricao
from app.models.gamificacao import Badge, Nivel, PontosXP, Streak, UsuarioBadge
from app.models.usuario import Usuario, UsuarioPerfil
from app.services.auth import hash_password
from app.services.gamificacao import calcular_nivel, atribuir_xp

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
            for tbl in ["lms.pontos_xp", "lms.usuario_badge", "lms.badges", "lms.inscricoes", "lms.cursos", "lms.usuario_perfil", "lms.streaks", "lms.niveis", "lms.usuarios"]:
                await session.execute(text(f"TRUNCATE {tbl} CASCADE"))
            niveis_exist = await session.scalar(text("SELECT COUNT(*) FROM lms.niveis"))
            if not niveis_exist:
                for i, (nome, xp, ordem) in enumerate([
                    ("Iniciante", 0, 1),
                    ("Bronze", 500, 2),
                    ("Prata", 1500, 3),
                    ("Ouro", 3000, 4),
                    ("Platina", 6000, 5),
                    ("Diamante", 10000, 6),
                    ("Mestre", 20000, 7),
                ]):
                    session.add(Nivel(nome=nome, xp_minimo=xp, ordem=ordem))
                await session.flush()
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

    async def test_level_up_after_xp(self, db_url):
        async def check(session, uid):
            nivel, prox = await calcular_nivel(session, uid)
            assert nivel.nome == "Iniciante"

            await atribuir_xp(session, usuario_id=uid, evento="curso_concluido", referencia_id=1, descricao="Curso 1")
            await atribuir_xp(session, usuario_id=uid, evento="curso_concluido", referencia_id=2, descricao="Curso 2")
            await atribuir_xp(session, usuario_id=uid, evento="curso_concluido", referencia_id=3, descricao="Curso 3")

            nivel, prox = await calcular_nivel(session, uid)
            assert nivel.nome == "Bronze"
            assert nivel.xp_minimo == 500
        await self._run_with_session(db_url, check)

    async def test_login_streak_xp_dinamico(self, db_url):
        async def check(session, uid):
            session.add(Streak(usuario_id=uid, dias_consecutivos=5, maior_streak=5))
            await session.flush()

            pts = await atribuir_xp(session, usuario_id=uid, evento="login_streak", referencia_id=1)
            assert pts is not None
            assert pts.quantidade == 50

            pts2 = await atribuir_xp(session, usuario_id=uid, evento="login_streak", referencia_id=1)
            assert pts2 is None
        await self._run_with_session(db_url, check)

    async def test_login_streak_sem_streak_retorna_none(self, db_url):
        async def check(session, uid):
            pts = await atribuir_xp(session, usuario_id=uid, evento="login_streak", referencia_id=1)
            assert pts is None
        await self._run_with_session(db_url, check)

    async def test_badge_auto_award(self, db_url):
        async def check(session, uid):
            badge = Badge(nome="Primeiro Curso", descricao="Conclua 1 curso", criterio_tipo="cursos_concluidos", criterio_valor=1)
            session.add(badge)
            await session.flush()

            curso = Curso(titulo="Curso Teste")
            session.add(curso)
            await session.flush()

            session.add(Inscricao(usuario_id=uid, curso_id=curso.id, status="concluido"))
            await session.flush()

            pts = await atribuir_xp(session, usuario_id=uid, evento="primeiro_acesso_dia", referencia_id=99)
            assert pts is not None

            badge_qtd = await session.scalar(
                select(func.count(UsuarioBadge.badge_id)).where(UsuarioBadge.usuario_id == uid)
            )
            assert badge_qtd == 1

            curso2 = Curso(titulo="Curso Teste 2")
            session.add(curso2)
            await session.flush()
            session.add(Inscricao(usuario_id=uid, curso_id=curso2.id, status="concluido"))
            await session.flush()

            pts2 = await atribuir_xp(session, usuario_id=uid, evento="primeiro_acesso_dia", referencia_id=100)
            assert pts2 is not None

            badge_qtd2 = await session.scalar(
                select(func.count(UsuarioBadge.badge_id)).where(UsuarioBadge.usuario_id == uid)
            )
            assert badge_qtd2 == 1
        await self._run_with_session(db_url, check)
