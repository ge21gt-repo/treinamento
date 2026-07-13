from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, avaliacoes, certificados, comunicacao, conteudos, cursos, dashboard, entregas, gamificacao, sandbox, scorm, sessoes, trilhas, usuarios, credenciamento
from app.config import settings
from app.database import engine
from app.models import Base
from app.services.rbac import PERFIL_PERMISSOES

@asynccontextmanager
async def lifespan(application: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS lms"))
        await conn.run_sync(Base.metadata.create_all)
        # Seed default profiles
        await conn.execute(text("""
            INSERT INTO lms.perfis (nome, descricao) VALUES
                ('administrador_geral', 'Gerencia a plataforma, autoriza instrutores, controla permissoes e acessos, acompanha indicadores gerais, realiza auditorias'),
                ('administrador', 'Gestao de cursos e usuarios'),
                ('instrutor', 'Cria cursos, cria trilhas de aprendizagem, cria avaliacoes, gerencia conteudos, autoriza gestores'),
                ('auditor', 'Visualizacao de relatorios e dashboards'),
                ('gestor', 'Autoriza funcionarios, acompanha treinamentos, visualiza dashboards, emite relatorios, monitora desempenho da equipe'),
                ('participante', 'Participa de cursos e trilhas, realiza avaliacoes, acompanha seu progresso, emite certificados')
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
        
        # Seed permissions for each profile (RBAC)
        for perfil_nome, permissoes in PERFIL_PERMISSOES.items():
            permissoes_json = "{" + ", ".join(f'"{p}": true' for p in permissoes) + "}"
            await conn.execute(text(f"""
                UPDATE lms.perfis 
                SET permissoes = '{permissoes_json}'::jsonb
                WHERE nome = '{perfil_nome}'
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


@app.get("/health")
async def health():
    return {"status": "ok"}
