# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

An `AGENTS.md` also exists in this repo root (written for another coding agent, OpenCode) — it contains a detailed, running log of completed issues/US's. Skim it for historical context on *why* something was built a certain way; this file focuses on what you need to be productive right now.

## ⚠️ Critical rules

- **Never run commands silently.** Every bash/pytest/git/migration command must be explicitly described to the user before running — this project's own agent instructions (`AGENTS.md`) call this out as an absolute rule.
- **Pushing to `development` or `homologacao` triggers a real deploy.** `.github/workflows/deploy.yml` fires on push to those branches and deploys straight to the `dev`/`hom` AWS servers via SSM (no approval gate). Treat any push to these branches as a production-adjacent action worth confirming first.
- **Migrations run on container startup** via `verify_initial_db.py` (Dockerfile CMD, before uvicorn): empty schema → `create_all` + `alembic stamp head`, then always `alembic upgrade head`; a DB with tables but no `lms.alembic_version` makes the container exit 1. Before this, the deploy did not run migrations, and the boot's `create_all()` only creates missing **tables** — never **columns** or **indexes**. So a column-adding migration that was never applied is invisible until an endpoint `select()`s the table and returns a generic 500. **Always run `alembic upgrade head` against the target DB before the push that triggers the deploy**, and confirm with `GET /health` → `checks.migrations`. This broke dev and left hom silently broken for 7 days (post-mortem: issue #69).
- **Two git remotes exist:** `ge21` (`ge21gt-repo/treinamento`, the real org repo) and `origin` (`laudares26/treinamento`, a personal fork). Check which remote a push is going to.

## Setup & Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit DATABASE_URL + SECRET_KEY
alembic upgrade head
psql $DATABASE_URL -f scripts/init_db.sql     # schema lms, extensions, seeds, indexes
uvicorn app.main:app --reload                 # dev server on :8000
```

The app **also auto-creates tables and seeds** (profiles, niveis, RBAC permissions, badges, forum terms, default certificate template) on every startup via the FastAPI `lifespan` in `app/main.py` — so `alembic upgrade head` + `init_db.sql` can be skipped for local dev, but always run them for staging/prod.

## Tests

Tests are **real integration tests** — no mocks. Each suite hits a real PostgreSQL database and real (or local-disk) storage over HTTP via `httpx.AsyncClient` against the actual `app`.

```bash
pytest                                        # full suite
pytest tests/test_us17.py -v                  # one file
pytest tests/test_us17.py::test_nome -v       # one test
pytest -m "not db" -v                         # skip tests requiring a live Postgres
```

- Uses `TEST_DATABASE_URL` if set (falls back to `DATABASE_URL`) — keep this pointed at a disposable DB, `tests/conftest.py` truncates most tables between tests (`db_clean` fixture, `TRUNCATE ... CASCADE`, keeps `perfis`/`forum_termos_bloqueados`).
- `db_clean` / per-test fixtures each open their **own** `create_async_engine` to avoid pool corruption; `event_loop` and `asyncio_default_test_loop_scope` are session-scoped (`pytest.ini`).
- The `client` fixture overrides `get_db` and `get_current_user` (defaults to an admin user) via `app.dependency_overrides` — build other-role tests by overriding `get_current_user` again inside the test, not by re-authenticating.
- Tests force `STORAGE_BACKEND=local` unless `TEST_STORAGE_BACKEND` is set.

## Lint / Format

Ruff is configured (`pyproject.toml`) and enforced in CI — run it before pushing:

```bash
ruff check .
ruff format --check .
```

CI (`.github/workflows/ci.yml`) also does an import smoke-test (`from app.main import app`) and runs the full pytest suite against a real Postgres service container.

## Architecture

```
app/
├── api/           # FastAPI route modules, ~1 per domain (auth, usuarios, cursos, trilhas, conteudos,
│                  # entregas, scorm, avaliacoes, gamificacao, sessoes, comunicacao, certificados,
│                  # dashboard, sandbox, credenciamento, auditoria, notificacoes, health, rate_limit, deps)
├── models/        # SQLAlchemy 2.0 models, all under schema `lms`
├── schemas/       # Pydantic v2 schemas (model_config, not orm_mode)
├── services/       # Business logic: rbac, auth, credenciamento, progresso, storage, teams, email,
│                  # scorm-adjacent, gamificacao, auditoria, log_acesso, moderacao, notificacoes,
│                  # certificados/certificado_templates, analytics, paginacao, chunked_upload, sandbox
├── config.py      # Settings from .env (pydantic-settings)
├── database.py    # Async engine + session factory
└── main.py        # Entrypoint: lifespan (auto-migrate/seed + periodic metrics job), middleware, routers
```

**Always update `app/api/__init__.py`, `app/models/__init__.py`, `app/schemas/__init__.py`** when adding new route modules, models, or schemas.

### Router prefix

All routes live under `/api/v1`; `main.py` passes `prefix=PREFIX` to each `include_router()`. Do **not** hardcode `/api/v1` inside individual router files. `health` is the one router mounted with no prefix (`/health`, used by the deploy workflow's health check).

### Key quirks

- **DB schema is `lms`** — every model has `__table_args__ = {"schema": "lms"}`; migrations/raw queries must specify it too.
- **Alembic is async** (`env.py` uses `async_engine_from_config`); set `sqlalchemy.url` via env override, not `alembic.ini`.
- **`DATABASE_URL` normalization** — `config.py` auto-converts `postgres://`/`postgresql://` to `postgresql+asyncpg://` and strips `?sslmode=` (applies to `TEST_DATABASE_URL` too).
- **Migration chain is non-linear** — several revisions use hash-style ids (e.g. `b98e1d3fd3ed`, `ad9d802fbf09`) chained by `down_revision`, not the numbered `NNN_*` files alone. Check `alembic heads` / the actual `down_revision` pointer before adding a new one, don't assume the highest numbered file is HEAD. Head as of 09/09/2026: `c7d3e9a1f204`.
- **Request logging middleware is raw ASGI** (not `BaseHTTPMiddleware`) in `main.py` — it also fires an async, best-effort `LogAcesso` write for every authenticated POST/PATCH/PUT/DELETE (US-17 audit trail), swallowing failures so logging never breaks a request.
- **Rate limiting** via `slowapi` (`app/api/rate_limit.py`, default `200/day, 50/hour` per remote address), wired as a global exception handler in `main.py`.
- **CORS** defaults to `["http://localhost:3000"]`, configurable via `.env`; `X-Total-Count` is an explicitly exposed header (pagination).

### Auth & Credenciamento

- 6 profiles seeded on startup: `administrador_geral`, `administrador`, `instrutor`, `auditor`, `gestor`, `participante`.
- Registering with a role creates a **pending** solicitation (`status="pendente"`) — the user is inactive until a superior approves them.
- Hierarchy: `admin_geral > admin > instrutor > gestor > participante`. Each role approves roles below it.
- `require_credenciamento` (`app/api/deps.py`) blocks unaccredited users; logic lives in `app/services/credenciamento.py`, endpoints in `app/api/credenciamento.py`.

### RBAC

- Permissions are constants (`Permissoes`) + a `PERFIL_PERMISSOES` dict in `app/services/rbac.py` — no DB query per-request, just a dict lookup, seeded into `Perfil.permissoes` JSONB on startup.
- `require_permissao(permissao: str)` in `app/api/deps.py` is a dependency factory: `Depends(require_permissao(Permissoes.AVALIACAO_CRIAR))`.
- A user can hold **multiple profiles** — permission checks must be `any(has_permission(p.nome, permissao) for p in perfis)`, not a single-profile lookup (a prior bug used `scalar_one_or_none()` and broke multi-profile users).
- `gestor` cannot create evaluations/comments but can create participant accounts (`POST /usuarios/criar-subordinado`).
- `instrutor` can sandbox-test via `POST /sandbox/iniciar` (tracked by `SandboxSessao`); sandbox actions are discarded on `.../encerrar`.

### Cursos & Trilhas

- Hierarchy: `TrilhaAprendizagem → Curso → Modulo → Unidade`, all in `app/models/curso.py` / `app/schemas/curso.py`.
- Trilha endpoints: `app/api/trilhas.py`. Curso/modulo/unidade/aula/chat endpoints: `app/api/cursos.py`.
- Progress is tracked at three levels and cascades bottom-up via `app/services/progresso.py`: `ProgressoUnidade` → `Inscricao` (course) → `InscricaoTrilha` (trail, avg of course progress).
- `Inscricao.nota_final` is computed server-side from the best-of results when a course is completed (`_nota_final_do_curso` helper) — never trust a client-supplied grade.

### Storage & uploads

- `app/services/storage.py` abstracts S3 (`aioboto3`) vs local disk via `STORAGE_BACKEND`. Uploaded objects are **private**; `url_acesso` is a presigned URL valid 1h (falls back to `url_arquivo` under local storage). Schemas exposing it: `ConteudoRead`, `MaterialComplementarRead`, `EntregaAtividadeRead`, `PacoteScormRead`, `ScormLaunchResponse`, `UnidadeRead`, `CursoArvoreItem`.
- SCORM (1.2/2004): `POST /scorm/upload` parses `imsmanifest.xml`; `GET /scorm/{id}/launch` issues a JWT + player URL; tracking is an upsert keyed by (usuario, pacote, sco_id).

### Teams integration

Two independent flows, both hit `AulaSincrona` fields:
- **Automatic** (`app/services/teams.py`, Microsoft Graph): `criar_reuniao_teams=true` on aula creation creates an online meeting; `POST /cursos/aulas/{id}/processar-gravacao` later pulls the recording, uploads it to storage, and links it via `gravacao_conteudo_id`. Requires Azure AD app permissions (`OnlineMeetings.ReadWrite.All`, `OnlineMeetingRecording.Read.All`, `OnlineMeetingAttendanceReport.Read.All`) — not configured in most environments, so creating with `criar_reuniao_teams=true` without config returns a 422 warning instead of silently no-oping.
- **Manual**: instructor pastes an external `link_externo` (Teams/Zoom/Meet), then uploads the recording afterward through `POST /conteudos/upload` and links it via `PATCH /cursos/aulas/{id}`.

### Auditoria (US-17)

- `LogAcesso` (every authenticated write, via middleware) and `LogAuditoria` (explicit before/after diffs on CRUD in cursos/usuarios/trilhas/avaliacoes/badges/missoes, via `app/services/auditoria.py`) are separate tables/concerns — don't conflate them.
- `GET /auditoria/logs` supports filters + CSV/PDF export, gated by `auditoria:visualizar`.

### Gamificação

- XP, niveis, badges, missoes, streaks, leaderboard live in `app/services/gamificacao.py` + `app/api/gamificacao.py`.
- Badge/mission progress is re-evaluated retroactively (`verificar_badges`, `atualizar_progresso_missoes`) on profile view and on manual badge grant — be careful not to recurse (a mission reward re-triggering mission-progress re-evaluation previously caused duplicate `usuario_missao` rows / login 500s).
- Leaderboard excludes management profiles (`NOT IN` the 5 admin-ish profiles) rather than filtering "participante only".

## Schema drift entre ambientes

The DB schema in each environment is `create_all()` **plus** whatever migrations happened to be applied there
by hand — not a clean migration chain. Consequences worth knowing before touching a real environment:

- `create_all()` satisfies *table-creating* migrations by accident (so `alembic_version` never advances) but
  satisfies *nothing* for column- or index-adding ones. The result is a hybrid schema that looks fine at boot.
- **A "migrations reproduce the models" test is impossible here:** migration `001` is an `ALTER` on `usuarios`,
  so the chain assumes `create_all` built the base. The test DB is also built by `create_all`, so it always
  matches the models by construction and can never see environment drift.
- The safety net is therefore runtime, not tests: `check_migrations()` in `app/services/health.py` compares
  `lms.alembic_version` against the code's head and lists pending revisions. It is surfaced in `GET /health`
  → `checks.migrations` and logged loudly at boot. It is **deliberately excluded from the overall `status`**,
  because the deploy uses that endpoint as a gate requiring HTTP 200 and stale schema doesn't stop the app from
  running — it just needs to be visible. `tests/test_health.py::TestDeteccaoDeSchemaAtrasado` guards it.
- **Reconciling a desynced environment:** don't run `upgrade head` blindly — it will try to recreate tables
  `create_all` already made and fail with "already exists". Sequence: `upgrade <rev genuinely missing>` →
  `stamp <rev whose tables already exist>` → `upgrade head`. Before stamping, diff columns **and indexes** —
  whatever the stamp skips, alembic will never apply again.
- When adding an index, declare it in the model with an explicit `Index("<exact migration name>", "<col>")`
  in `__table_args__`, not `index=True` (which produces `ix_<schema>_<table>_<col>` and would create a
  duplicate alongside the migration's).

## Conventions when changing the schema

- **When modifying a model** (adding a field/constraint): update the Pydantic schema, the API response model, the JWT payload if the frontend needs it, and add an Alembic migration chained off the actual current head (see migration-chain quirk above).
- **When adding a DB constraint** (unique/FK/not-null): validate it in the route *before* insert and catch `IntegrityError` → return 4xx, never let it surface as a 500.
- **Seeding via raw SQL** (`text()`): every `NOT NULL` column needs an explicit value — SQLAlchemy model defaults don't apply to raw `INSERT`s, and a missing one crashes app startup (this took down hom/dev once).
- Before merging anything that touches startup seeding, actually exercise the `lifespan` locally (or run `pytest tests/test_boot.py`) rather than trusting that `create_all` + seeds will succeed against a real DB.
