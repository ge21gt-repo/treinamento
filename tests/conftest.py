import asyncio
import json
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "480")

from app.config import settings

# Testes usam TEST_STORAGE_BACKEND quando definido (ex: s3); padrao local
if settings.TEST_STORAGE_BACKEND:
    os.environ["STORAGE_BACKEND"] = settings.TEST_STORAGE_BACKEND
    settings.STORAGE_BACKEND = settings.TEST_STORAGE_BACKEND
else:
    os.environ["STORAGE_BACKEND"] = "local"
    settings.STORAGE_BACKEND = "local"

# Tests usam TEST_DATABASE_URL se definido, senao DATABASE_URL
_TEST_DB_URL = settings.TEST_DATABASE_URL or settings.DATABASE_URL
settings.DATABASE_URL = _TEST_DB_URL
os.environ["DATABASE_URL"] = _TEST_DB_URL

from app.api.deps import get_current_user, get_db
from app.database import engine as app_engine
from app.main import app
from app.models import Base
from app.models.usuario import Usuario, UsuarioPerfil
from app.services.auth import create_access_token, hash_password
from app.services.rbac import PERFIL_PERMISSOES

TEST_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_PARTICIPANTE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TEST_GESTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_setup():
    from sqlalchemy.ext.asyncio import create_async_engine

    _engine = create_async_engine(_TEST_DB_URL)
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
                text(
                    "INSERT INTO lms.perfis (nome, descricao) VALUES (:nome, :descricao) ON CONFLICT (nome) DO NOTHING"
                ),
                {"nome": nome, "descricao": descricao},
            )

        for perfil_nome, permissoes in PERFIL_PERMISSOES.items():
            permissoes_json = "{" + ", ".join(f'"{p}": true' for p in permissoes) + "}"
            await conn.execute(
                text(f"UPDATE lms.perfis SET permissoes = '{permissoes_json}'::jsonb WHERE nome = :nome"),
                {"nome": perfil_nome},
            )

        from app.services.moderacao import TERMOS_DEFAULT
        from app.models.comunicacao import ForumTermoBloqueado

        for item in TERMOS_DEFAULT:
            await conn.execute(
                text(
                    "INSERT INTO lms.forum_termos_bloqueados (termo, categoria, ativo) "
                    "VALUES (:termo, :categoria, true) ON CONFLICT (termo) DO NOTHING"
                ),
                {"termo": item["termo"], "categoria": item["categoria"]},
            )
    await _engine.dispose()
    yield


@pytest_asyncio.fixture
async def db_clean(db_setup):
    from sqlalchemy.ext.asyncio import create_async_engine

    _clean_engine = create_async_engine(_TEST_DB_URL)
    async with _clean_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in ("perfis", "forum_termos_bloqueados"):
                await conn.execute(text(f"TRUNCATE TABLE lms.{table.name} CASCADE"))
    await _clean_engine.dispose()
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


@pytest.fixture
def keycloak_admin_fake(monkeypatch):
    """Substitui a Admin API do Keycloak por fakes, sem rede.

    A criacao de usuario passou a chamar o Keycloak (issue #116); sem isto,
    qualquer teste que crie subordinado tentaria falar com o servidor real.
    """
    from app.services import keycloak_admin as ka

    chamadas = {"criados": [], "roles": [], "emails": [], "removidos": [], "habilitados": []}

    async def criar_usuario(email, nome, *, habilitado=True):
        chamadas["criados"].append((email, nome))
        return f"kc-{len(chamadas['criados'])}"

    async def definir_role(sub, perfil):
        chamadas["roles"].append((sub, perfil))

    async def enviar_email_de_acao(sub, acoes=None):
        chamadas["emails"].append(sub)

    async def remover_usuario(sub):
        chamadas["removidos"].append(sub)

    async def definir_habilitado(sub, habilitado):
        chamadas["habilitados"].append((sub, habilitado))

    monkeypatch.setattr(ka, "criar_usuario", criar_usuario)
    monkeypatch.setattr(ka, "definir_role", definir_role)
    monkeypatch.setattr(ka, "enviar_email_de_acao", enviar_email_de_acao)
    monkeypatch.setattr(ka, "remover_usuario", remover_usuario)
    monkeypatch.setattr(ka, "definir_habilitado", definir_habilitado)
    return chamadas

@pytest_asyncio.fixture
async def admin_user(db_clean):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    _eng = create_async_engine(_TEST_DB_URL)
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
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    _eng = create_async_engine(_TEST_DB_URL)
    _session_maker = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
    session = _session_maker()
    try:
        user = await _create_user(
            session, TEST_PARTICIPANTE_ID, "participante@test.com", "Participante", "participante"
        )
        await _assign_perfil(session, user.id, "participante")
        await session.commit()
        yield user
    finally:
        await session.close()
        await _eng.dispose()


@pytest_asyncio.fixture
async def gestor_user(db_clean):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    _eng = create_async_engine(_TEST_DB_URL)
    _session_maker = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
    session = _session_maker()
    try:
        user = await _create_user(session, TEST_GESTOR_ID, "gestor@test.com", "Gestor", "gestor")
        await _assign_perfil(session, user.id, "gestor")
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


class _AsyncWebSocketConnection:
    """Cliente WebSocket ASGI async — roda a app no MESMO loop do pytest (sem
    thread, sem lifespan, sem conflito de loop). Emula a interface do
    TestClient.websocket_connect, mas assíncrona.
    """

    def __init__(self, app, path: str, subprotocols: list[str] | None = None):
        self._app = app
        self._path = path
        self._subprotocols = subprotocols or []
        self._from_app: asyncio.Queue = asyncio.Queue()  # app -> cliente
        self._to_app: asyncio.Queue = asyncio.Queue()  # cliente -> app
        self._task: asyncio.Task | None = None

    # --- callables passados para o app (interface ASGI) ---
    # O app chama `receive()` para ler mensagens do cliente e `send(msg)` para
    # entregar mensagens ao cliente.

    async def _receive(self):
        # O que o cliente envia -> fila `_to_app`.
        return await self._to_app.get()

    async def _send(self, message):
        # O que o app envia -> fila `_from_app`.
        await self._from_app.put(message)

    # --- cliente ---

    async def _open(self):
        # Separa path e query string (?token=...) como o servidor faria.
        raw_path = self._path
        query_string = b""
        if "?" in raw_path:
            path_part, query_part = raw_path.split("?", 1)
            raw_path = path_part
            query_string = query_part.encode()
        headers = [
            (b"host", b"testserver"),
            (b"connection", b"upgrade"),
            (b"upgrade", b"websocket"),
            (b"sec-websocket-key", b"test"),
            (b"sec-websocket-version", b"13"),
        ]
        if self._subprotocols:
            headers.append((b"sec-websocket-protocol", ", ".join(self._subprotocols).encode()))
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": raw_path,
            "raw_path": raw_path.encode(),
            "root_path": "",
            "query_string": query_string,
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "subprotocols": self._subprotocols,
        }
        self._task = asyncio.create_task(self._app(scope, self._receive, self._send))
        # Handshake: envia "connect" e aguarda "accept" ou "close".
        await self._to_app.put({"type": "websocket.connect"})
        while True:
            message = await self._from_app.get()
            if message["type"] == "websocket.accept":
                return
            if message["type"] == "websocket.close":
                raise WebSocketDisconnect(code=message.get("code", 1000))

    async def _close(self):
        # Avisa a app que o cliente fechou a conexao e espera a task terminar.
        try:
            self._to_app.put_nowait({"type": "websocket.disconnect", "code": 1000})
        except Exception:
            pass
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass

    async def send_json(self, payload):
        await self._to_app.put({"type": "websocket.receive", "text": json.dumps(payload)})

    async def receive_json(self):
        while True:
            message = await self._from_app.get()
            if message["type"] == "websocket.send":
                return json.loads(message["text"])
            if message["type"] == "websocket.close":
                raise WebSocketDisconnect(code=message.get("code", 1000))

    async def __aenter__(self):
        await self._open()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._close()


@pytest_asyncio.fixture
async def ws_client(client):
    """Cliente WebSocket ASGI async para testes.

    Roda a app no mesmo event loop do pytest-asyncio — sem thread separada, sem
    `lifespan` (o banco de teste ja tem as tabelas), sem cruzar loops. Com isso,
    o `RuntimeError: attached to a different loop` (TestClient sincrono + WS +
    pytest-asyncio) deixa de existir e os testes WS ficam deterministicos, mesmo
    em lote.
    """
    from app.main import app

    class _WSClient:
        def websocket_connect(self, path: str, subprotocols: list[str] | None = None):
            return _AsyncWebSocketConnection(app, path, subprotocols)

    yield _WSClient()
    # Limpa o registro global de conexoes WS para nao vazar entre testes.
    try:
        from app.api.cursos import _ws_connections

        _ws_connections.clear()
    except Exception:
        pass


@pytest_asyncio.fixture
async def client(admin_user, admin_token):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    _client_eng = create_async_engine(_TEST_DB_URL)

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
