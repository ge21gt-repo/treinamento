import logging
import logging.config
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api import (
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
    sandbox,
    scorm,
    sessoes,
    trilhas,
    usuarios,
)
from app.api.rate_limit import limiter
from app.config import settings
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
                ('Intermediario', 500, 2),
                ('Avancado', 1500, 3),
                ('Especialista', 3500, 4),
                ('Mestre', 7000, 5)
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
    logger.info("Database seeded successfully")
    yield
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
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.now(timezone.utc)
    response = await call_next(request)
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(
        "%s %s -> %s (%.3fs)",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


PREFIX = "/api/v1"

app.include_router(health.router)
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
