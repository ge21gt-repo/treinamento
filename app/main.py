from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, avaliacoes, certificados, comunicacao, conteudos, cursos, dashboard, gamificacao, sessoes, trilhas, usuarios
from app.config import settings
from app.database import engine
from app.models import Base

@asynccontextmanager
async def lifespan(application: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS lms"))
        await conn.run_sync(Base.metadata.create_all)
        # Seed default profiles
        await conn.execute(text("""
            INSERT INTO lms.perfis (nome, descricao) VALUES
                ('administrador_geral', 'Acesso total ao sistema'),
                ('administrador', 'Gestao de cursos e usuarios'),
                ('instrutor', 'Criacao de conteudo e avaliacoes'),
                ('auditor', 'Visualizacao de relatorios e dashboards'),
                ('participante', 'Acesso as trilhas e cursos')
            ON CONFLICT (nome) DO NOTHING
        """))
        # Seed gamification levels
        await conn.execute(text("""
            INSERT INTO lms.niveis (nome, xp_minimo, ordem) VALUES
                ('Iniciante', 0, 1),
                ('Intermediario', 500, 2),
                ('Avancado', 1500, 3),
                ('Especialista', 3500, 4),
                ('Mestre', 7000, 5)
            ON CONFLICT (nome) DO NOTHING
        """))
    yield
    await engine.dispose()


app = FastAPI(
    title="LMS IDE-SP",
    description="API da Plataforma de Capacitacao e Treinamento IDE-SP",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"

app.include_router(auth.router, prefix=PREFIX)
app.include_router(usuarios.router, prefix=PREFIX)
app.include_router(trilhas.router, prefix=PREFIX)
app.include_router(cursos.router, prefix=PREFIX)
app.include_router(conteudos.router, prefix=PREFIX)
app.include_router(avaliacoes.router, prefix=PREFIX)
app.include_router(gamificacao.router, prefix=PREFIX)
app.include_router(sessoes.router, prefix=PREFIX)
app.include_router(comunicacao.router, prefix=PREFIX)
app.include_router(certificados.router, prefix=PREFIX)
app.include_router(dashboard.router, prefix=PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok"}
