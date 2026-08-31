import asyncio
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
    auth,
    auditoria,
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
            permissoes_json = "{" + ", ".join(f'"{p}": true' for p in permissoes) + "}"
            await conn.execute(
                text(f"""
                UPDATE lms.perfis
                SET permissoes = '{permissoes_json}'::jsonb
                WHERE nome = '{perfil_nome}'
            """)
            )

        # Seed termos bloqueados do forum (US-14) — apenas se tabela vazia
        from app.services.moderacao import seed_termos_default

        async with AsyncSessionLocal() as seed_session:
            await seed_termos_default(seed_session)

        # Seed modelo padrao de certificado (US-15) — apenas se tabela vazia
        from app.services.certificado_templates import TEMPLATE_CERTIFICADO_PADRAO

        template_padrao = TEMPLATE_CERTIFICADO_PADRAO().replace("'", "''")
        await conn.execute(
            text(f"""
            INSERT INTO lms.modelos_certificado (nome, template_html, logo_url, assinatura_digital, ativo)
            SELECT 'Padrao GE21', '{template_padrao}', NULL, false, true
            WHERE NOT EXISTS (SELECT 1 FROM lms.modelos_certificado)
            """)
        )
    logger.info("Database seeded successfully")

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


async def _registrar_acesso_escrita(method: str, path: str, authorization: str) -> None:
    """Grava log_acesso de operacoes de escrita (T-17.1), sem bloquear a resposta."""
    if method not in ("POST", "PATCH", "DELETE", "PUT"):
        return
    if not authorization or not authorization.startswith("Bearer "):
        return
    from app.services.auth import decode_token

    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        return
    try:
        import uuid

        from app.database import async_session
        from app.models.log import LogAcesso

        async with async_session() as db:
            db.add(LogAcesso(usuario_id=uuid.UUID(payload["sub"]), acao=method, recurso_tipo="route", recurso_id=None))
            await db.commit()
    except Exception:
        pass


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

        import asyncio

        auth = b""
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                auth = v.decode()
        asyncio.create_task(_registrar_acesso_escrita(scope["method"], scope["path"], auth))

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
