# AGENTS.md — Plataforma de Treinamento LMS (backend)

## Stack

- **Python 3.12** + **FastAPI** + **SQLAlchemy 2.0 async** + **asyncpg**
- **PostgreSQL 15+** — all tables in schema `lms`
- **Alembic** (async) for migrations
- **Auth:** JWT (python-jose) + bcrypt (passlib)

## Setup & Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit DATABASE_URL + SECRET_KEY
alembic upgrade head
psql $DATABASE_URL -f scripts/init_db.sql     # seeds + indexes
uvicorn app.main:app --reload                 # dev server port 8000
```

The app **also auto-creates tables, seeds profiles and niveis** on startup via FastAPI lifespan — so `alembic upgrade head` + `init_db.sql` may be skipped for local dev, but use them for staging/prod.

## Key Quirks

- **DB schema is `lms`** — every model table has `__table_args__ = {"schema": "lms"}`. Migrations and queries must specify `schema="lms"`.
- **Alembic is async** — env.py uses `async_engine_from_config`. Set `sqlalchemy.url` via env override, not alembic.ini.
- **DATABASE_URL normalization** — `config.py` auto-converts `postgres://` or `postgresql://` to `postgresql+asyncpg://` and strips `?sslmode=`. On Fly.io (`.flycast` in URL), SSL is disabled.
- **Lifespan auto-migrate** — `app.main.py` runs `Base.metadata.create_all` and seeds profiles/niveis on every startup. Do not rely on this in prod; use Alembic.
- **CORS** defaults to `["http://localhost:3000"]`, configurable via `.env`.
- **`.env` vars:** `DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` (default 480), `CORS_ORIGINS`.

## Dev Workflow

- **No tests exist** yet — no pytest config, no test files, no test command.
- **No linter/formatter/typechecker config** — no ruff, flake8, mypy, black, isort. CI only checks that `from app.main import app` works.
- **CI** (`.github/workflows/ci.yml`): runs on push/PR to `main`, installs deps, runs `python -c "from app.main import app; print(len(app.routes))"`.
- **Deploy** (`fly.io`): `fly deploy` via GitHub Actions or manually. Dockerfile serves on port 8080.

## Architecture

```
app/
├── api/           # FastAPI route modules (1 per domain)
├── models/        # SQLAlchemy models
├── schemas/       # Pydantic v2 schemas
├── services/      # Business logic (empty __init__.py)
├── config.py      # Settings from .env
├── database.py    # Async engine + session factory
└── main.py        # App entrypoint with lifespan
```

**Always update `app/api/__init__.py`, `app/models/__init__.py`, `app/schemas/__init__.py`** when adding new route modules, models, or schemas.

### Router prefix

All routes are under `/api/v1`. `main.py` passes `prefix=PREFIX` to each `include_router`. Do NOT add `/api/v1` prefixes inside individual router files.

### Auth & Credenciamento

- **6 profiles** seeded on startup: `administrador_geral`, `administrador`, `instrutor`, `auditor`, `gestor`, `participante`.
- **Registration creates a pending solicitation** (`status="pendente"`) — user is inactive until approved by a superior.
- **Hierarchical approval:** `admin_geral` > `admin` > `instrutor` > `gestor` > `participante`. Each role can approve roles below them.
- **Middleware** (`require_credenciamento` in `app/api/deps.py`) blocks unaccredited users.
- **Credentials module:** `app/services/credenciamento.py` (logic), `app/api/credenciamento.py` (endpoints).

### RBAC (US-03)

- **Permissions** defined in `app/services/rbac.py` as `Permissoes` constants and `PERFIL_PERMISSOES` mapping.
- **`require_permissao(permissao: str)`** in `app/api/deps.py` is a factory that returns a dependency. Usage: `Depends(require_permissao(Permissoes.AVALIACAO_CRIAR))`.
- **Profile → permissions mapped:** dict lookup in `PERFIL_PERMISSOES` (no DB query). Seeds to `Perfil.permissoes` JSONB on startup.
- **Gestor** cannot create evaluations/comments (`avaliacao:criar`, `comentario:criar`). Can create student accounts via `POST /api/v1/usuarios/criar-subordinado`.
- **Instrutor** can sandbox via `POST /api/v1/sandbox/iniciar` — tracked by `SandboxSessao` model.
- **Sandbox endpoints:** `iniciar`, `{id}/encerrar`, `ativo`, `sessoes` — all require `sandbox:testar` permission.

### Cursos & Trilhas (Estrutura Existente)

- **Hierarchy:** TrilhaAprendizagem → Curso → Modulo → Unidade
- **Models:** All in `app/models/curso.py` (TrilhaAprendizagem, Curso, Modulo, Unidade, Inscricao, ProgressoUnidade)
- **Schemas:** All in `app/schemas/curso.py` (Pydantic models for all entities)
- **Endpoints:**
  - Trilhas: `app/api/trilhas.py` (GET/POST/PATCH/DELETE /api/v1/trilhas)
  - Cursos: `app/api/cursos.py` (complete CRUD for cursos, modulos, unidades, inscricoes, progresso)
- **Progress tracking:**
  - Course level: `Inscricao` table (status, progresso_pct, data_conclusao, nota_final)
  - Unit level: `ProgressoUnidade` table (status, tempo_gasto, concluido_em)
- **Missing:** Trail-level progress tracking (user → trail enrollment + aggregated progress)

## Project State

- **Branch:** `devin-issue13`
- **Roadmap:** 23/72 tasks done (31.9%). US-04 ✅, US-05 ✅, Pendências Técnicas ✅.
- **Previous milestones:** Credenciamento flow (tasks 18-26), RBAC (tasks 17.2-17.3, 30.1), US-04 (Trilhas), US-05 (Cursos avançado).
- **Current Sprint:** Sprint 3 - Próximas US (Estrutura Organizacional / Dashboards)
- **Structure of Courses & Trails:** ALREADY IMPLEMENTED (TrilhaAprendizagem, Curso, Modulo, Unidade, Inscricao, ProgressoUnidade)
- **Endpoints for Trails:** ALREADY IMPLEMENTED (GET/POST/PATCH/DELETE /api/v1/trilhas)
- **Endpoints for Courses:** ALREADY IMPLEMENTED (complete CRUD for cursos, modulos, unidades, inscricoes, progresso)
- **3 Alembic migrations** exist: `001_add_credenciamento_fields`, `002_add_tokens_reset_senha`, `003_add_aulas_chat_unidades`. Chain new ones with `down_revision` pointing to the latest migration.
- **`scripts/init_db.sql`** creates the `lms` schema, extensions (`pgcrypto`, `citext`), seeds profiles/niveis, and adds performance indexes — it is idempotent (uses `ON CONFLICT DO NOTHING`).

## Convictions

- Always add imports in `__init__.py` for new models/schemas.
- Only 1 migration exists; chain new ones with `down_revision` pointing to `'001_add_credenciamento_fields'`.
- Use Pydantic v2 style (no `orm_mode`, use `model_config`).
- SQLAlchemy 2.0 style — use `select()`, `await db.execute()`, no `Query` API.

## Issues em Andamento

### Sprint 2 - US-04: Gestão de Trilhas de Aprendizagem
**Status:** Task 1 da Sprint 2 - Planejamento inicial

**Análise de estrutura existente:**
- ✅ **Models implementados:** `TrilhaAprendizagem`, `Curso`, `Modulo`, `Unidade`, `Inscricao`, `ProgressoUnidade` (app/models/curso.py)
- ✅ **Schemas implementados:** Todos os schemas Pydantic para trilhas e cursos (app/schemas/curso.py)
- ✅ **Endpoints trilhas:** CRUD completo em app/api/trilhas.py (GET/POST/PATCH/DELETE /api/v1/trilhas)
- ✅ **Endpoints cursos:** CRUD completo em app/api/cursos.py (cursos, modulos, unidades, inscricoes, progresso)
- ✅ **Relacionamentos:** Trilha ↔ Curso ↔ Modulo ↔ Unidade (com cascade delete)
- ✅ **Sistema de progresso:** Inscricao (curso level) + ProgressoUnidade (unidade level)

**Escopo da US-04 (segundo descrição):**
- Interface paginada vertical para trilhas
- Sistema de progresso de trilha (agregado dos cursos)
- Participante seguir percursos formativos estruturados

**Gap identificado:**
- ❌ **Progresso de trilha:** Não existe model/table para rastrear progresso do usuário em uma trilha (só existe progresso de curso)
- ❌ **Endpoints de progresso de trilha:** Não existem endpoints para inscrever usuário em trilha ou listar progresso
- ❌ **Lógica de progresso agregado:** Precisa calcular progresso de trilha com base nos cursos da trilha
- ❌ **Interface paginada vertical:** Isso é frontend (não aplicável ao backend atual)

**O que falta implementar para US-04 completa:**
1. Model `InscricaoTrilha` ou `ProgressoTrilha` para rastrear matrícula/progresso em trilhas
2. Endpoint para inscrever usuário em trilha
3. Endpoint para listar trilhas do usuário com progresso
4. Lógica de cálculo de progresso de trilha (média dos cursos da trilha)
5. Permissões RBAC específicas para trilhas (trilha:criar, trilha:inscrever, etc.)

### US-03: Gestão de Perfis e Controle de Acesso (RBAC) ✅ CONCLUÍDA
**Issue GitHub:** #6

**Status:** Concluída em 01/07/2026 (implementado pelo opencode)

**Escopo implementado:**
- ✅ Sistema de permissões granular (RBAC)
- ✅ Middleware de verificação de permissões
- ✅ Endpoint para listar usuários por perfil
- ✅ Gestor criar conta de participante (subordinado)
- ✅ Sandbox do instrutor para testar avaliações/comentários

**Regras de negócio (refinamento da reunião):**
- ✅ Gestor não preenche/salva avaliações (apenas fiscaliza)
- ✅ Gestor pode criar conta tipo aluno
- ✅ Instrutor pode testar em sandbox
- ✅ Hierarquia: ADM > Instrutor > Gestor > Aluno

**Tasks do ROADMAP afetadas:**
- ✅ Task 3: Listar usuários por perfil
- ✅ Task 17.1: Gestor criar subordinado
- ✅ Task 17.2: Sistema RBAC (movido de Extremamente Complexas)
- ✅ Task 17.3: Middleware de permissões (movido de Extremamente Complexas)
- ✅ Task 30.1: Sandbox instrutor

**Arquivos criados/modificados (pelo opencode):**
- app/services/rbac.py (sistema RBAC)
- app/api/deps.py (require_permissao)
- app/api/usuarios.py (filtro por perfil, criar subordinado)
- app/api/sandbox.py (endpoints sandbox)
- app/models/sandbox.py (model SandboxSessao)
- app/schemas/sandbox.py (schemas sandbox)
- app/main.py (seed de permissões)
- app/api/__init__.py (imports sandbox)
- app/models/__init__.py (imports SandboxSessao)
- app/schemas/__init__.py (imports sandbox schemas)
- ROADMAP.md (tarefas marcadas como concluídas)
