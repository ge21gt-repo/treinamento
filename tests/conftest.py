import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/lms_idesp_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "480")

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.database import engine as app_engine
from app.main import app
from app.models import Base
from app.models.curso import Curso, Modulo, TrilhaAprendizagem, Unidade
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.services.auth import create_access_token, hash_password
from app.services.rbac import PERFIL_PERMISSOES

TEST_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_PARTICIPANTE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_setup():
    from sqlalchemy.ext.asyncio import create_async_engine
    _engine = create_async_engine(settings.DATABASE_URL)
    async with _engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS lms"))
        await conn.run_sync(Base.metadata.create_all)

        perfis_data = [
            ("administrador_geral", "Gerencia total da plataforma"),
            ("administrador", "Gestao de cursos e usuarios"),
            ("instrutor", "Cria cursos e avaliacoes"),
            ("auditor", "Visualizacao de relatorios"),
            ("gestor", "Autoriza funcionarios"),
            ("participante", "Participa de cursos"),
        ]
        for nome, descricao in perfis_data:
            await conn.execute(
                text("INSERT INTO lms.perfis (nome, descricao) VALUES (:nome, :descricao) ON CONFLICT (nome) DO NOTHING"),
                {"nome": nome, "descricao": descricao},
            )

        for perfil_nome, permissoes in PERFIL_PERMISSOES.items():
            permissoes_json = "{" + ", ".join(f'"{p}": true' for p in permissoes) + "}"
            await conn.execute(
                text(f"UPDATE lms.perfis SET permissoes = '{permissoes_json}'::jsonb WHERE nome = :nome"),
                {"nome": perfil_nome},
            )
    await _engine.dispose()
    yield


@pytest_asyncio.fixture
async def db_clean(db_setup):
    await app_engine.dispose()
    async with app_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "perfis":
                await conn.execute(text(f"TRUNCATE TABLE lms.{table.name} CASCADE"))
    yield


async def _create_user(session, id, email, nome, perfil_nome, status="aprovado"):
    user = Usuario(
        id=id,
        nome_completo=nome,
        email=email,
        senha_hash=hash_password("test123"),
        ativo=True,
        status_credenciamento=status,
        aceite_lgpd=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _assign_perfil(session, usuario_id, perfil_nome):
    result = await session.execute(
        text("SELECT id FROM lms.perfis WHERE nome = :nome"),
        {"nome": perfil_nome},
    )
    perfil_id = result.scalar_one()
    up = UsuarioPerfil(usuario_id=usuario_id, perfil_id=perfil_id)
    session.add(up)
    await session.flush()


@pytest_asyncio.fixture
async def admin_user(db_clean):
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    _eng = create_async_engine(settings.DATABASE_URL)
    _session_maker = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
    session = _session_maker()
    try:
        user = await _create_user(session, TEST_ADMIN_ID, "admin@test.com", "Admin Geral", "administrador_geral")
        await _assign_perfil(session, user.id, "administrador_geral")
        await session.commit()
        yield user
    finally:
        await session.close()
        await _eng.dispose()


@pytest_asyncio.fixture
async def participante_user(db_clean):
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    _eng = create_async_engine(settings.DATABASE_URL)
    _session_maker = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
    session = _session_maker()
    try:
        user = await _create_user(session, TEST_PARTICIPANTE_ID, "participante@test.com", "Participante", "participante")
        await _assign_perfil(session, user.id, "participante")
        await session.commit()
        yield user
    finally:
        await session.close()
        await _eng.dispose()


@pytest_asyncio.fixture
async def admin_token(admin_user):
    return create_access_token(
        data={"sub": str(admin_user.id), "email": admin_user.email},
    )


@pytest_asyncio.fixture
async def client(admin_user, admin_token):
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    _client_eng = create_async_engine(settings.DATABASE_URL)

    async def override_get_db():
        _maker = async_sessionmaker(_client_eng, class_=AsyncSession, expire_on_commit=False)
        session = _maker()
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers.update({"Authorization": f"Bearer {admin_token}"})
        yield ac

    app.dependency_overrides.clear()
    await _client_eng.dispose()
