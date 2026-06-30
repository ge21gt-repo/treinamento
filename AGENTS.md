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

## Project State

- **Branch:** `devin`
- **Roadmap:** 15/62 tasks done (24.2%). US-03 (RBAC) complete — tasks 3, 17.1-17.3, 30.1 done.
- **Previous milestones:** Credenciamento flow (tasks 18-26), RBAC (tasks 17.2-17.3).
- **Only 1 Alembic migration** exists (`001_add_credenciamento_fields_to_usuario`). Adding new fields/models requires creating a new migration.
- **`scripts/init_db.sql`** creates the `lms` schema, extensions (`pgcrypto`, `citext`), seeds profiles/niveis, and adds performance indexes — it is idempotent (uses `ON CONFLICT DO NOTHING`).

## Convictions

- Always add imports in `__init__.py` for new models/schemas.
- Only 1 migration exists; chain new ones with `down_revision` pointing to `'001_add_credenciamento_fields'`.
- Use Pydantic v2 style (no `orm_mode`, use `model_config`).
- SQLAlchemy 2.0 style — use `select()`, `await db.execute()`, no `Query` API.

## Issues em Andamento

### US-03: Gestão de Perfis e Controle de Acesso (RBAC) 🔲 ABERTA
**Issue GitHub:** #6

**Escopo:**
- Sistema de permissões granular (RBAC)
- Middleware de verificação de permissões
- Endpoint para listar usuários por perfil
- Gestor criar conta de participante (subordinado)
- Sandbox do instrutor para testar avaliações/comentários

**Regras de negócio (refinamento da reunião):**
- Gestor não preenche/salva avaliações (apenas fiscaliza)
- Gestor pode criar conta tipo aluno
- Instrutor pode testar em sandbox
- Hierarquia: ADM > Instrutor > Gestor > Aluno

**Tasks do ROADMAP afetadas:**
- Task 3: Listar usuários por perfil
- Task 17.1: Gestor criar subordinado
- Task 17.2: Sistema RBAC (movido de Extremamente Complexas)
- Task 17.3: Middleware de permissões (movido de Extremamente Complexas)
- Task 30.1: Sandbox instrutor

**Estimativa:** 6-8 horas

**Pré-requisitos:** US-02 (fluxo de credenciamento) ✅
