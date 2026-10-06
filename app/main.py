import asyncio
import json
import logging
import logging.config
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api import (
    auditoria,
    auth,
    avaliacoes,
    certificados,
    comunicacao,
    conteudos,
    credenciamento,
    cursos,
    dashboard,
    entregas,
    gamificacao,
    health,
    notificacoes,
    sandbox,
    scorm,
    sessoes,
    trilhas,
    usuarios,
)
from app.api.rate_limit import limiter
from app.config import settings
from app.database import async_session as AsyncSessionLocal
from app.database import engine
from app.models import Base
from app.services.rbac import PERFIL_PERMISSOES

logger = logging.getLogger(__name__)

# Logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if settings.ENV != "development" else "standard",
            "level": "INFO",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "app": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "sqlalchemy.engine": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
logging.config.dictConfig(LOGGING_CONFIG)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Starting application - seeding database")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS lms"))
        await conn.run_sync(Base.metadata.create_all)
        # Seed default profiles
        await conn.execute(
            text("""
            INSERT INTO lms.perfis (nome, descricao) VALUES
                ('administrador_geral', 'Gerencia a plataforma, autoriza instrutores, controla permissoes e acessos'),
                ('administrador', 'Gestao de cursos e usuarios'),
                ('instrutor', 'Cria cursos, trilhas, avaliacoes, gerencia conteudos, autoriza gestores'),
                ('auditor', 'Visualizacao de relatorios e dashboards'),
                ('gestor', 'Autoriza funcionarios, gerencia treinamentos, dashboards, relatorios'),
                ('participante', 'Participa de cursos e trilhas, realiza avaliacoes, emite certificados')
            ON CONFLICT (nome) DO NOTHING
        """)
        )
        # Seed gamification levels
        await conn.execute(
            text("""
            INSERT INTO lms.niveis (nome, xp_minimo, ordem) VALUES
                ('Iniciante', 0, 1),
                ('Bronze', 500, 2),
                ('Prata', 1500, 3),
                ('Ouro', 3000, 4),
                ('Platina', 6000, 5),
                ('Diamante', 10000, 6),
                ('Mestre', 20000, 7)
            ON CONFLICT (nome) DO UPDATE SET xp_minimo = EXCLUDED.xp_minimo, ordem = EXCLUDED.ordem
        """)
        )
        # Remove niveis do seed antigo (issue 13.2)
        await conn.execute(
            text("DELETE FROM lms.niveis WHERE nome IN ('Intermediario', 'Avancado', 'Especialista')")
        )

        # Seed badges (issue 13.3)
        await conn.execute(
            text("""
            INSERT INTO lms.badges (nome, descricao, criterio_tipo, criterio_valor, ativo) VALUES
                ('Primeiro passo', 'Conclua seu primeiro curso', 'cursos_concluidos', 1, true),
                ('Maratonista', 'Conclua 5 cursos', 'cursos_concluidos', 5, true),
                ('Constante', 'Mantenha uma sequencia de 7 dias', 'dias_streak', 7, true),
                ('Dedicado', 'Conclua 10 unidades', 'unidades_concluidas', 10, true),
                ('Veterano', 'Acumule 1000 XP', 'xp_acumulado', 1000, true),
                ('Trilheiro', 'Conclua sua primeira trilha', 'trilhas_concluidas', 1, true)
            ON CONFLICT (nome) DO NOTHING
        """)
        )

        # Seed permissions for each profile (RBAC)
        for perfil_nome, permissoes in PERFIL_PERMISSOES.items():
            permissoes_json = {p: True for p in permissoes}
            await conn.execute(
                text("""
                UPDATE lms.perfis
                SET permissoes = CAST(:permissoes AS jsonb)
                WHERE nome = :nome
            """),
                {"permissoes": json.dumps(permissoes_json), "nome": perfil_nome},
            )

        # Seed termos bloqueados do forum (US-14) — apenas se tabela vazia
        from app.services.moderacao import seed_termos_default

        async with AsyncSessionLocal() as seed_session:
            await seed_termos_default(seed_session)

        # Seed modelo padrao de certificado (US-15) — apenas se tabela vazia
        from app.services.certificado_templates import TEMPLATE_CERTIFICADO_PADRAO

        template_padrao = TEMPLATE_CERTIFICADO_PADRAO()
        await conn.execute(
            text("""
            INSERT INTO lms.modelos_certificado (nome, template_html, logo_url, assinatura_digital, ativo)
            SELECT 'Padrao GE21', :template, NULL, false, true
            WHERE NOT EXISTS (SELECT 1 FROM lms.modelos_certificado)
            """),
            {"template": template_padrao},
        )
    logger.info("Database seeded successfully")

    # Smoke-test do bucket S3 configurado (issue 46) -- so avisa, nunca derruba o start.
    from app.services.storage import verificar_bucket_disponivel

    if await verificar_bucket_disponivel():
        logger.info("Bucket S3 respondeu no boot")

    # Schema atrasado em relacao ao codigo e silencioso ate um endpoint quebrar
    # com 500: o deploy nao roda `alembic upgrade head` e o create_all acima so
    # cria tabela que falta, nunca coluna. Avisa alto no boot.
    from app.services.health import check_migrations

    async with AsyncSessionLocal() as check_session:
        migracoes = await check_migrations(check_session)
    if migracoes["status"] == "ok":
        logger.info("Migrations: %s", migracoes["detail"])
    else:
        logger.warning(
            "MIGRATIONS DESATUALIZADAS - endpoints podem responder 500 por coluna inexistente. %s",
            migracoes["detail"],
        )

    # Job periodico: coleta diaria de metricas de engajamento (US-16, T-16.1)
    from app.services.analytics import coletar_metricas_diarias

    async def _job_metricas_diarias():
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # 6h apos o start; depois 1x/dia
                async with AsyncSessionLocal() as job_session:
                    await coletar_metricas_diarias(job_session)
                    await job_session.commit()
                logger.info("Metricas de engajamento coletadas (job diario)")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Falha na coleta de metricas: %s", e)

    job_task = asyncio.create_task(_job_metricas_diarias())
    yield
    job_task.cancel()
    try:
        await job_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down - disposing database engine")
    await engine.dispose()


app = FastAPI(
    title="LMS IDE-SP",
    description="API da Plataforma de Capacitacao e Treinamento IDE-SP",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path=settings.ROOT_PATH.rstrip("/"),
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception in %s %s: %s", request.method, request.url.path, exc)
    headers = {}
    origin = request.headers.get("origin")
    if settings.CORS_ORIGINS and origin in settings.CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
        headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
        headers=headers,
    )


app.add_exception_handler(Exception, _unhandled_exception_handler)


# Cache curto em memoria: sub -> usuario.id, para nao ir ao banco a cada
# requisicao so para resolver o usuario (issue #100). Expira em 5 min.
_SUB_TO_USUARIO_ID: dict[str, str] = {}
_SUB_CACHE_AT: float = 0.0
_SUB_CACHE_TTL = 300


async def _resolver_usuario_id_por_token(db, token: str) -> str | None:
    """Resolve o usuario.id do token (Keycloak RS256 ou HS256 interno).

    Issue #100: antes o middleware so aceitava HS256 (decode_token), entao quem
    entra pelo Keycloak nao era registrado. Agora tenta Keycloak primeiro
    (valida RS256 e busca por keycloak_sub) e so depois cai no HS256 interno.
    """
    from sqlalchemy import select

    from app.models.usuario import Usuario
    from app.services.auth import decode_token
    from app.services.keycloak import validar_token_keycloak

    # 1) Keycloak (RS256)
    kc_payload = validar_token_keycloak(token)
    if kc_payload and kc_payload.get("sub"):
        sub = str(kc_payload["sub"])
        user = (
            await db.execute(select(Usuario).where(Usuario.keycloak_sub == sub))
        ).scalar_one_or_none()
        if user:
            return str(user.id)
        return None

    # 2) HS256 interno
    payload = decode_token(token)
    if payload and payload.get("sub"):
        return str(payload["sub"])
    return None


# Issue #68: as tasks de log_acesso eram "soltas" (fire-and-forget sem referencia).
# Sob escrita densa, uma delas podia ficar pendurada em "idle in transaction"
# segurando um lock na tabela, travando outras escritas por minutos. Agora sao
# rastreadas e o commit tem timeout.
_LOG_ACESSO_TASKS: set = set()


def _disparar_log_acesso(method: str, path: str, authorization: str) -> None:
    task = asyncio.create_task(_registrar_acesso_escrita(method, path, authorization))
    _LOG_ACESSO_TASKS.add(task)
    task.add_done_callback(_LOG_ACESSO_TASKS.discard)


async def _registrar_acesso_escrita(method: str, path: str, authorization: str) -> None:
    """Grava log_acesso de operacoes de escrita (T-17.1), sem bloquear a resposta.

    Resolve o usuario pelo mesmo caminho do get_current_user: Keycloak (RS256,
    por keycloak_sub) e depois HS256 interno. Usa cache curto sub->id.
    """
    if method not in ("POST", "PATCH", "DELETE", "PUT"):
        return
    if not authorization or not authorization.startswith("Bearer "):
        return
    token = authorization.split(" ", 1)[1]
    try:
        import uuid

        from app.database import async_session
        from app.models.log import LogAcesso

        async with async_session() as db:
            usuario_id = await _resolver_usuario_id_por_token(db, token)
            if not usuario_id:
                return

            # Issue #82: gravar o path da rota em recurso_tipo (ex.: /api/v1/cursos/5)
            # e o id numerico (se houver) em recurso_id, em vez de "route"/None fixos.
            recurso_id = None
            import re

            m = re.search(r"/(\d+)(?:/|$)", path)
            if m:
                recurso_id = int(m.group(1))

            db.add(
                LogAcesso(
                    usuario_id=uuid.UUID(usuario_id),
                    acao=method,
                    recurso_tipo=path[:50],
                    recurso_id=recurso_id,
                )
            )
            # Issue #68: timeout no commit. Se o commit nao completar num prazo
            # curto (lock/contencao), cancela e faz rollback para nao deixar a
            # conexao "idle in transaction" segurando lock.
            try:
                await asyncio.wait_for(db.commit(), timeout=10)
            except Exception:
                await db.rollback()
    except Exception:
        pass


# Security headers middleware (raw ASGI, no BaseHTTPMiddleware)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "X-XSS-Protection": "1; mode=block",
}


class SecurityHeadersMiddleware:
    """Adiciona headers de seguranca em toda resposta HTTP (OWASP)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for name, value in SECURITY_HEADERS.items():
                    headers.append((name.lower().encode(), value.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)

# Request logging middleware (raw ASGI, no BaseHTTPMiddleware)
class LogRequestsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = datetime.now(timezone.utc)
        status_code = [0]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        auth = b""
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                auth = v.decode()
        _disparar_log_acesso(scope["method"], scope["path"], auth)

        duration = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info(
            "%s %s -> %s (%.3fs)",
            scope["method"],
            scope["path"],
            status_code[0],
            duration,
        )

app.add_middleware(LogRequestsMiddleware)

PREFIX = "/api/v1"

app.include_router(notificacoes.router, prefix=PREFIX)
app.include_router(health.router)
app.include_router(auditoria.router, prefix=PREFIX)
app.include_router(auth.router, prefix=PREFIX)
app.include_router(usuarios.router, prefix=PREFIX)
app.include_router(trilhas.router, prefix=PREFIX)
app.include_router(cursos.router, prefix=PREFIX)
app.include_router(conteudos.router, prefix=PREFIX)
app.include_router(entregas.router, prefix=PREFIX)
app.include_router(scorm.router, prefix=PREFIX)
app.include_router(avaliacoes.router, prefix=PREFIX)
app.include_router(gamificacao.router, prefix=PREFIX)
app.include_router(sessoes.router, prefix=PREFIX)
app.include_router(comunicacao.router, prefix=PREFIX)
app.include_router(certificados.router, prefix=PREFIX)
app.include_router(dashboard.router, prefix=PREFIX)
app.include_router(sandbox.router, prefix=PREFIX)
app.include_router(credenciamento.router, prefix=PREFIX)
