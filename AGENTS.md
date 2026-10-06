# AGENTS.md — Plataforma de Treinamento LMS (backend)

## ⚠️ REGRA ABSOLUTA

**NUNCA RODAR NADA SILENCIOSAMENTE.** Todo comando/bash/git deve ser explicitamente descrito com `description=""` claro. Nada de rodar pytest, migrations, scripts, ou qualquer operação sem o usuário saber o que está sendo executado. Sempre explicar o que vai rodar ANTES de rodar.

## Stack

- **Python 3.12** + **FastAPI** + **SQLAlchemy 2.0 async** + **asyncpg**
- **PostgreSQL 15+** — all tables in schema `lms`
- **Alembic** (async) for migrations
- **Auth:** JWT (python-jose) + bcrypt (passlib)
- **Storage:** S3 (aioboto3) or local disk for file uploads
- **Teams Integration:** Microsoft Graph API (httpx) for synchronous classes
- **Email:** SMTP service for password recovery

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
- **`.env` vars:** `DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` (default 480), `CORS_ORIGINS`, `STORAGE_BACKEND` (local/s3), `S3_*` (S3 config), `TEAMS_*` (Teams integration), `SMTP_*` (email), `BASE_URL`, `RESET_TOKEN_EXPIRE_MINUTES`, `MAX_UPLOAD_SIZE`, `TEST_DATABASE_URL`, `TEST_STORAGE_BACKEND`, `TEST_S3_BUCKET`.

## Dev Workflow

- **Tests:** 35 test files (auth, RBAC, US-04..08, US-11..17, fixes). Run with `pytest`.
- **Test Database:** Uses `TEST_DATABASE_URL` (database-2, senha separada) — isolado do dev. Bucket S3 de teste: `lms-conteudos-teste`.
- **Test infrastructure:** `pytest.ini` uses `asyncio_default_test_loop_scope = session`. Raw ASGI middleware (no BaseHTTPMiddleware). `db_clean` fixture uses separate engine to avoid pool corruption. `event_loop` fixture is session-scoped. Tests override `STORAGE_BACKEND=local`.
- **Ruff IS configured and enforced in CI** (`pyproject.toml`) — run `ruff check .` and `ruff format --check .` before pushing. CI also does an import smoke-test (`from app.main import app`) and runs pytest against a real Postgres service container. (No mypy/black/isort.)
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
- **Models:** All in `app/models/curso.py` (TrilhaAprendizagem, Curso, Modulo, Unidade, Inscricao, ProgressoUnidade, InscricaoTrilha, MensagemCurso, AulaSincrona)
- **Schemas:** All in `app/schemas/curso.py` (Pydantic models for all entities)
- **Endpoints:**
  - Trilhas: `app/api/trilhas.py` (GET/POST/PATCH/DELETE /api/v1/trilhas + inscrever/progresso/minhas-trilhas)
  - Cursos: `app/api/cursos.py` (complete CRUD for cursos, modulos, unidades, inscricoes, progresso, aulas, chat, consumo, arvore)
- **Progress tracking:**
  - Trail level: `InscricaoTrilha` table (status, progresso_pct, data_inscricao, data_conclusao)
  - Course level: `Inscricao` table (status, progresso_pct, data_conclusao, nota_final)
  - Unit level: `ProgressoUnidade` table (status, tempo_gasto, concluido_em)
- **Progress service:** `app/services/progresso.py` handles cascade updates (unidade → curso → trilha)

## Project State

- **Base branches:** `development` (principal), `homologacao`, `devin/1782154515-backend-lms`, `main` (production, PR → deploy).
- **Work branches (fix/feature):** created from `development`, one per batch of issues, deleted after merging. None open as of 09/09/2026.
- **`devin/...`** is a "resguardo" (backup) branch kept in sync with `development`; not a deploy target.
- **Deploy flow:** pushing `development` deploys **dev**, `homologacao` deploys **hom** — GitHub Actions → tarball to S3 → AWS SSM → `docker build` + `docker compose up` on EC2 (`i-03226a7435365244a`). No approval gate.
- **THE CONTAINER RUNS MIGRATIONS ON STARTUP.** The `Dockerfile` CMD runs `python verify_initial_db.py` before uvicorn: empty `lms` schema → `create_all` + `alembic stamp head`; then always `alembic upgrade head` (no-op at head). Tables without `lms.alembic_version` (hybrid DB) → exits 1 and the container does not start; reconcile by hand. For hom/prod, still dry-run (`--sql`) and back up before pushing a new migration.
- **`/health`** now includes `check_migrations` and `check_database`/`check_storage`. `check_migrations` is intentionally excluded from the overall status: the deploy uses HTTP 200 as gate and a stale schema shouldn't fail the app. `GET /health` checks DB reachability and S3 access.
- **Roadmap:** US-04 ✅, US-05 ✅, US-06 ✅, US-07 ✅, US-08 ✅, Pendências Técnicas ✅, US-11/12/13/14 ✅, US-15/16/17 ✅ (certificados, dashboards/analytics, logs de auditoria), US-18 ✅ (integracao E2E, carga 10k, seguranca, LGPD). Issues 17-24, 25-31 done.
- **Known issues:** SMTP não configurado (`esqueci-senha` não envia emails). Teams: código pronto mas **não configurado** — precisa das 4 vars (`TEAMS_*`) no ambiente do deploy + Application Access Policy (PowerShell) do organizer; até lá `criar_reuniao_teams:true` retorna 422.
- **Alembic migrations:** 20 migrations. Head atual: `c7d3e9a1f204` (`conteudo_disponivel_marca_bucket_morto_issue_46`). Chain new ones with `down_revision` pointing to the current head — **never** to an old anchor.
- **`scripts/init_db.sql`** creates the `lms` schema, extensions (`pgcrypto`, `citext`), seeds profiles/niveis, and adds performance indexes — idempotent (`ON CONFLICT DO NOTHING`).

## Convictions

- **Testar o boot da app localmente antes de qualquer merge é obrigatório** — rodar o `lifespan`/start (ex.: `async with lifespan(app)`) para validar create_all + seeds. Incidente 14/08: seed sem coluna NOT NULL crashava o start e derrubou hom/dev (502).
- **O `create_all()` do boot cria TABELA que falta, nunca COLUNA nem ÍNDICE** — por isso o `verify_initial_db.py` roda `alembic upgrade head` antes do uvicorn. Migration que cria tabela fica satisfeita por acidente e o `alembic_version` nunca avança; migration que adiciona coluna não é satisfeita por nada. O banco fica híbrido e o sintoma só aparece quando um endpoint faz `select()` e devolve 500 genérico. **Incidente 08-09/09/2026:** `/cursos/{id}/consumo` 500 em todo curso no dev (faltava `conteudos.disponivel`); o hom ficou **7 dias quebrado em silêncio** na presença (faltava `presenca_aula.saida_estimada`), com deploys reportando sucesso porque o gate só checa HTTP 200. Post-mortem: issue #69.
- **Rode `alembic upgrade head` no banco alvo ANTES do push que dispara o deploy** — com `--sql` (dry-run) e backup antes, em hom/prod. Conferir depois com `alembic current` e `GET /health` → `checks.migrations`.
- **Se um ambiente estiver dessincronizado, não rode `upgrade head` direto** — ele tenta recriar tabelas que o `create_all` já fez e falha com "already exists". Reconcilie: `upgrade <rev que falta de verdade>` → `stamp <rev cujas tabelas já existem>` → `upgrade head`. **Antes do `stamp`, compare coluna a coluna E os índices** — o que o stamp pula, o alembic nunca mais aplica (foi assim que o `ix_notificacoes_usuario_id` quase se perdeu no hom).
- **Model e migration têm que contar a mesma história** — se a migration cria um índice, o model precisa declará-lo, senão todo banco nascido do `create_all` nasce sem. Cuidado com `index=True`: ele gera `ix_<schema>_<tabela>_<coluna>`, nome diferente do que a migration costuma usar — prefira `Index("<nome exato da migration>", "<coluna>")` no `__table_args__`.
- **Seed via SQL puro: TODAS as colunas NOT NULL explícitas** — o default do model SQLAlchemy não vale em `INSERT` via `text()`; sem isso o start crasha com `NotNullViolationError`.
- Always add imports in `__init__.py` for new models/schemas.
- Chain new migrations with `down_revision` pointing to the current head (see Project State), never an old anchor.
- Use Pydantic v2 style (no `orm_mode`, use `model_config`).
- SQLAlchemy 2.0 style — use `select()`, `await db.execute()`, no `Query` API.
- Run tests with `pytest` before major changes — 35 test files. Tests are slow (many require the PostgreSQL test DB) and can be flaky if the network/IP for the DB (AWS security group) is stale.
- **When modifying a model (adding field/constraint):**
  - [ ] Verify schema Pydantic reflects the change
  - [ ] Verify API response model includes the field
  - [ ] Verify route creates/updates the field properly
  - [ ] Verify JWT payload includes the field if needed by frontend
- **When adding a DB constraint (unique, FK, not-null):**
  - [ ] Add migration (alembic revision --autogenerate)
  - [ ] Validate constraint in the API route BEFORE insert (catch IntegrityError)
  - [ ] Return proper 4xx error (not 500) for constraint violations
- **When implementing RBAC:**
  - [ ] Verify the schema exposes `perfis`/roles in response
  - [ ] Verify JWT token includes profile claim for frontend use
  - [ ] Verify all profiles that should have the permission are mapped in `PERFIL_PERMISSOES`
- **When implementing a registration/creation route:**
  - [ ] Validate all unique fields (email, cpf, telefone) BEFORE insert
  - [ ] Handle IntegrityError gracefully → return 409/400, never 500
  - [ ] Every `unique=True` in model must have a corresponding check in the route


## Issues Concluídas

### Issue #18: BUG: AmbiguousForeignKeysError em Usuario.solicitacoes_credenciamento ✅ CONCLUÍDA
**Status:** Concluída em 13/07/2026

**Problema:** Erro ao cadastrar usuário via POST /api/v1/auth/registro com PostgreSQL real devido a ambiguidade de FKs na tabela SolicitacaoCredenciamento (2 FKs para usuarios: usuario_id e avaliado_por).

**Solução:** Adicionado `primaryjoin` explícito no relationship Usuario.solicitacoes_credenciamento em app/models/usuario.py para eliminar ambiguidade.

**Arquivos modificados:**
- app/models/usuario.py (adicionado primaryjoin)
- tests/conftest.py (alterado DATABASE_URL para usar PostgreSQL real do .env)
- tests/test_bug_fix_18.py (novos testes para validar o fix)

### Sprint 2 - US-04: Gestão de Trilhas de Aprendizagem ✅ CONCLUÍDA
**Issue GitHub:** #11 (pré-requisitos #9)

**Status:** Concluída em 02/07/2026

**Escopo implementado:**
- ✅ Model `InscricaoTrilha` (usuario_id, trilha_id, status, progresso_pct, data_inscricao, data_conclusao)
- ✅ Schemas Pydantic completos (InscricaoTrilhaCreate, InscricaoTrilhaRead, InscricaoTrilhaUpdate)
- ✅ Permissões RBAC: `trilha:criar`, `trilha:editar`, `trilha:excluir`, `trilha:inscrever`, `trilha:ver_progresso`
- ✅ Endpoints:
  - `POST /trilhas/{id}/inscrever` — inscrever usuário em trilha
  - `GET /trilhas/minhas-trilhas` — listar trilhas do usuário com progresso
  - `GET /trilhas/{id}/progresso` — progresso detalhado da trilha
- ✅ Filtro por nível em `GET /trilhas` e filtro por trilha em `GET /cursos`
- ✅ Cálculo de progresso agregado (média dos cursos da trilha)

**Arquivos criados/modificados:**
- app/models/curso.py (InscricaoTrilha)
- app/schemas/curso.py (schemas InscricaoTrilha)
- app/services/rbac.py (permissões trilha:*)
- app/api/trilhas.py (endpoints de progresso)
- app/services/progresso.py (cálculo de progresso de trilha)

### US-05: Gestão de Cursos, Módulos e Unidades ✅ CONCLUÍDA
**Issue GitHub:** #12

**Status:** Concluída em 08/07/2026

**Escopo implementado:**
- ✅ Sub-módulos tipados: `conteudo_url`, `url_externa` na model `Unidade`
- ✅ Aulas síncronas: Model `AulaSincrona` completo com Teams integration
- ✅ Chat contínuo por curso: Model `MensagemCurso` com endpoints e SSE streaming
- ✅ Reordenação de módulos/unidades: `PATCH /cursos/modulos/reorder` e `PATCH /cursos/unidades/reorder`
- ✅ Validação de pré-requisitos: existência, ciclo e bloqueio de inscrição
- ✅ Árvore de conteúdo: `GET /cursos/{id}/arvore`
- ✅ XR (redirecionamento externo): campo `url_externa` na `Unidade`
- ✅ 11 testes implementados

**Arquivos criados/modificados:**
- app/models/curso.py (MensagemCurso, AulaSincrona, campos Unidade)
- app/api/cursos.py (endpoints aulas, chat, reorder, arvore, consumo)
- app/services/teams.py (integração Microsoft Graph API)
- tests/test_us05.py (11 testes)

### US-06: Upload e Gestão de Conteúdos Multimídia ✅ CONCLUÍDA
**Issue GitHub:** #15

**Status:** Concluída em 13/07/2026

**Escopo implementado:**
- ✅ Serviço de upload S3/local (`app/services/storage.py`)
- ✅ Upload de vídeos, PDFs, áudio, imagens, SCORM
- ✅ Materiais complementares por curso
- ✅ Player de vídeo integrado
- ✅ Visualizador de PDF embutido
- ✅ Entrega de atividades: Model `EntregaAtividade` completo
- ✅ Endpoints:
  - `POST /conteudos/upload` — upload multipart
  - `POST /conteudos/materiais/upload` — materiais complementares
  - `POST /entregas/upload` — entregas de alunos
  - `PATCH /entregas/{id}/corrigir` — correção pelo instrutor
- ✅ Integração Teams (`app/services/teams.py`)
- ✅ Suporte a SCORM completo (PacoteScorm, TrackingScorm)
- ✅ RBAC de conteúdos (`conteudo:*`, `material:gerenciar`, `entrega:*`)
- ✅ Testes implementados

**Arquivos criados/modificados:**
- app/services/storage.py (upload S3/local)
- app/services/teams.py (integração Teams)
- app/models/scorm.py (PacoteScorm, TrackingScorm)
- app/api/entregas.py (endpoints entregas)
- app/api/scorm.py (endpoints SCORM)
- app/api/conteudos.py (endpoints upload)
- tests/test_us06.py (testes)

### US-07: Inscrição e Acompanhamento de Progresso ✅ CONCLUÍDA
**Issue GitHub:** #16

**Status:** Concluída em 13/07/2026

**Escopo implementado:**
- ✅ Serviço de progresso (`app/services/progresso.py`)
- ✅ Verificação de duplicidade ao inscrever
- ✅ `GET /cursos/inscricoes/minhas` — inscrições do próprio usuário
- ✅ `DELETE /cursos/inscricoes/{id}` — cancelar inscrição
- ✅ `POST /unidades/{id}/concluir` — marcar unidade como concluída
- ✅ Cálculo automático de progresso: unidade → curso → trilha (cascade)
- ✅ Dashboard pessoal: `GET /dashboard/meu-progresso`
- ✅ Barra de progresso visual por módulo e curso
- ✅ Testes de rastreamento de progresso

**Arquivos criados/modificados:**
- app/services/progresso.py (cálculo cascade de progresso)
- app/api/cursos.py (endpoints inscrições, progresso)
- app/api/dashboard.py (endpoint meu-progresso)
- tests/test_us07.py (testes)

### Pendências Técnicas US-02/US-03 ✅ CONCLUÍDAS
**Issue GitHub:** #13

**Status:** Concluída em 06/07/2026

**Escopo implementado:**
- ✅ Recuperação de senha: `POST /auth/esqueci-senha` + `POST /auth/redefinir-senha`
- ✅ Model `TokenResetSenha` completo
- ✅ Serviço de email SMTP (`app/services/email.py`)
- ✅ LGPD: validação de `aceite_lgpd` no cadastro
- ✅ CRUD de perfis completo: `PATCH /usuarios/perfis/{id}` + `DELETE /usuarios/perfis/{id}`
- ✅ Testes de autenticação (8 testes)
- ✅ Testes de RBAC (10 testes)

**Arquivos criados/modificados:**
- app/models/token_reset.py (TokenResetSenha)
- app/services/email.py (serviço SMTP)
- app/api/auth.py (endpoints recuperação senha)
- app/schemas/usuario.py (LGPD, PerfilUpdate)
- app/api/usuarios.py (CRUD perfis completo)
- tests/test_auth.py (8 testes)
- tests/test_rbac.py (10 testes)

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

### Issue #21: perfis no UsuarioRead e JWT ✅ CONCLUÍDA
**Issue GitHub:** #21

**Status:** Concluída em 15/07/2026

**Problema:** `UsuarioRead` não incluía campo `perfis` no response. JWT não continha claim `perfis` para uso no frontend.

**Solução:**
- Adicionado `perfis: list[PerfilRead]` ao schema `UsuarioRead`
- Adicionado `selectinload(Usuario.perfis)` em `get_current_user()`, registro, login, listar, obter, atualizar e criar-subordinado
- Corrigido MissingGreenlet no `PATCH /usuarios/{id}`

**Testes:** 6/6 (`tests/test_issue21_perfis.py`)

### Issue #22: validação de campos únicos antes do INSERT ✅ CONCLUÍDA
**Issue GitHub:** #22

**Status:** Concluída em 15/07/2026

**Problema:** Email, CPF e telefone duplicados geravam `IntegrityError 500` (exception não tratada).

**Solução:** Função `check_unique_fields()` em `app/api/auth.py` consulta o banco antes de inserir e retorna `409 Conflict` com mensagem específica por campo.

**Testes:** 6/6 (`tests/test_issue22_validacao.py`)

### Issue #23: unique constraint no telefone ✅ CONCLUÍDA
**Issue GitHub:** #23

**Status:** Concluída em 15/07/2026

**Solução:** Adicionado `unique=True` no campo `telefone` do model `Usuario` + migração Alembic `005_add_telefone_unique_constraint`. Validação pré-insert já captura duplicatas e retorna 409.

**Testes:** 5/5 (`tests/test_issue23_telefone.py`)

### Issue #26: Paginação sem X-Total-Count ✅ CONCLUÍDA
**Issue GitHub:** #26

**Status:** Concluída em 20/07/2026

**Problema:** Endpoints paginados não retornavam total de registros — frontend não sabia quantas páginas existem.

**Solução:**
- Novo serviço `app/services/paginacao.py` com helpers `count_query()` e `apply_search()`
- 9 endpoints paginados agora retornam header `X-Total-Count` com total de registros
- Backward compatible — sem mudança no envelope de resposta

**Arquivos criados/modificados:**
- app/services/paginacao.py (novo)
- app/api/avaliacoes.py, cursos.py, trilhas.py, conteudos.py, sessoes.py, comunicacao.py, dashboard.py, usuarios.py

### Issue #27: Busca por query string (ILIKE) ✅ CONCLUÍDA
**Issue GitHub:** #27

**Status:** Concluída em 20/07/2026

**Problema:** Nenhum endpoint suportava busca textual — frontend precisava filtrar no cliente.

**Solução:**
- 7 endpoints aceitam `?q=...` para busca server-side com ILIKE
- Endpoints: usuários, cursos, trilhas, avaliações, conteúdos, sessões, fórum
- Chat e logs excluídos conforme especificação

**Arquivos modificados:**
- app/api/avaliacoes.py, cursos.py, trilhas.py, conteudos.py, sessoes.py, comunicacao.py, usuarios.py
- app/services/paginacao.py (helper `apply_search`)

### Proteção RBAC: POST /usuarios/perfis/atribuir ✅ IMPLEMENTADO

**Status:** Concluída em 20/07/2026

**Problema:** Endpoint de atribuição de perfil não tinha proteção RBAC — qualquer usuário autenticado podia chamar.

**Solução:**
- Adicionada permissão `Permissoes.PERFIL_ATRIBUIR = "perfil:atribuir"`
- Mapeada para `administrador_geral` e `administrador` em `PERFIL_PERMISSOES`
- Endpoint `POST /usuarios/perfis/atribuir` agora usa `Depends(require_permissao(Permissoes.PERFIL_ATRIBUIR))`

### US-12: Frequência (Presença) ✅ CONCLUÍDA
**Status:** Concluída em 19/08/2026 (merge `f9476a1` homolog / `73698a0` dev-devin)

**Escopo implementado:**
- ✅ Model `Presenca`/`PresencaAula` (sessão/aula, usuário, entrada/saída, tempo, IP)
- ✅ Registro de presença, atualização de saída, listagem por sessão/aula
- ✅ Consulta administrativa agregada (`/cursos/aulas/presencas`)
- ✅ Relatório CSV e PDF (`/cursos/aulas/{aula_id}/presencas/relatorio?formato=csv|pdf`)
- ✅ Fechamento lazy de presenças abertas de aulas já encerradas
- ✅ Integração Teams (sincronizar presença, processar gravação)
- ✅ 12 testes (`tests/test_us12.py`)

**Fix aplicado:** `POST /sessoes/presenca` com sessão inexistente retornava **500** (FK violation não tratada) — agora valida a sessão antes do INSERT e retorna **404**; `IntegrityError` de usuário inexistente vira **400**. Teste novo em `tests/test_sessoes.py` (`test_registrar_presenca_sessao_inexistente_404`).

### US-13: Chat em Tempo Real ✅ CONCLUÍDA
**Status:** Concluída em 19/08/2026 (merge `f9476a1` homolog / `73698a0` dev-devin)

**Escopo implementado:**
- ✅ Model `MensagemAula` (chat por aula) + SSE `/cursos/{curso_id}/chat/stream` (Server-Sent Events via `StreamingResponse`, não WebSocket)
- ✅ Model `MensagemCurso` (chat por curso) — endpoints GET/POST `/cursos/{curso_id}/chat`
- ✅ Moderação: silenciar usuário (`silenciado_ate` na `usuarios`), excluir mensagem
- ✅ 11 testes (`tests/test_us13.py`)

### US-14: Fórum de Discussão ✅ CONCLUÍDA
**Status:** Concluída em 19/08/2026 (merge `f9476a1` homolog / `73698a0` dev-devin)

**Escopo implementado:**
- ✅ Fórum por curso: tópicos, respostas, fixar, fechar, excluir
- ✅ Moderação: tabela `forum_termos_bloqueados` + serviço `app/services/moderacao.py` (normalização de acentos, termos bloqueados rejeitados com 422)
- ✅ 20 testes (`tests/test_us14.py`)

### Migrations 009/010/011 (US-13/US-14) ✅
- `009` (`b98e1d3fd3ed`): tabela `mensagens_aula`
- `010` (`bcbc58716d17`): coluna `silenciado_ate` em `usuarios`
- `011` (`ff5220e8f1ca`): tabela `forum_termos_bloqueados`
- Encadeadas após `013` (cadeia única: `008→012→013→009→010→011`), head único `ff5220e8f1ca`

### Migration 014 (Issue 22) ✅
- `014` (`de126b1182f8`): índice único `uq_usuario_missao (usuario_id, missao_id)`

### Issues 17-24 (ciclo de fixes 19/08-25/08) ✅ CONCLUÍDAS
Todas as 8 issues levantadas pelo front foram corrigidas, validadas em dev e homologadas (merge `57aa5db` homolog / `10f2942` dev-devin).

- **17** — `aguardando_correcao` conta só dissertativas da MESMA avaliação (`Questao.avaliacao_id` no count) + `GET /avaliacoes/resultados/{usuario_id}` consistente
- **18** — `GET /badges?incluir_inativas=true` (restrito a `gamificacao:criar`) + `conquistas: int` no `BadgeRead`
- **19** — `LogAcessoRead`/`LogAuditoriaRead` com `IPvAnyAddress` + field_serializer (fim do 500); filtros `acao`/`data_inicio`/`data_fim` em `/logs`; login usa `X-Forwarded-For`
- **20** — `Inscricao.nota_final` preenchida ao concluir (média das melhores notas, helper `_nota_final_do_curso`); `scripts/backfill_nota_final.py` recalcula concluídas; `submeter` cria o Resultado ANTES de concluir unidade
- **21** — badges/missões retroativas: `verificar_badges` + `atualizar_progresso_missoes` rodam em `/perfil` e `/badges/progresso`; `POST /badges` concede a quem já cumpre; missões valem para todos (cria `usuario_missao` automático — PEND-25)
- **22** — `participar_missao` idempotente + índice único; `GET /missoes/{id}/participantes`; aluno vê próprio histórico
- **23** — leaderboard exclui perfis de gestão (`NOT IN` 5 perfis administrativos, não filtro por participante); valida `origem` de XP contra `EVENTOS_XP` + chama `atribuir_xp`; rota `GET /leaderboard/minha-posicao` (posição mesmo fora do top N, `no_ranking: true` quando fora do grupo, XP medido no mesmo conjunto filtrado)
- **24** — `GET /leaderboard?curso_id=N` filtra ranking pelos inscritos do curso (turma = `lms.inscricoes`)

### US-15: Certificados Digitais ✅ CONCLUÍDA
- **T-15.1** — Modelos personalizáveis (HTML template) + seed de modelo padrão (cria on-demand se faltar)
- **T-15.2** — Emissão automática ao concluir o curso (sem duplicar: usuario_id+curso_id; emite com ou sem avaliação)
- **T-15.3** — PDF via reportlab (paisagem): nome, CPF mascarado, prefeitura, curso, carga horária, nota, data, código
- **T-15.4** — QR Code (lib `qrcode`) + hash SHA-256
- **T-15.5** — Página pública de validação `GET /certificados/validar/{hash}/pagina` (HTML, sem login)
- **T-15.6** — `GET /certificados/meus` (participante, sem permissão admin)
- **T-15.7** — 8 testes (`tests/test_us15.py`). Dep `qrcode>=7.4`.

### US-16: Dashboards e Analytics ✅ CONCLUÍDA
- **T-16.1** — Coleta diária de métricas (job asyncio 1x/dia no lifespan + `POST /dashboard/metricas/coletar` para backlog); `app/services/analytics.py`
- **T-16.2** — `GET /dashboard/kpis`: inscritos, concluídos, evasão, taxa, nota média (filtros período/curso)
- **T-16.3** — `GET /dashboard/graficos/temporal` (dia/semana/mês)
- **T-16.4** — `GET /dashboard/relatorios/desempenho` (curso/trilha)
- **T-16.5** — `GET /dashboard/relatorios/presenca` (consolidado por período)
- **T-16.6** — `formato=csv|pdf` nos relatórios (helpers `_csv_stream`/`_pdf_simples`)
- **T-16.7** — filtros dinâmicos (período, curso, perfil); **RBAC** `dashboard:kpis/graficos/relatorios` para gestor+admin+auditor
- **T-16.8** — 16 testes (`tests/test_us16.py`)

### US-17: Logs de Auditoria e Rastreabilidade ✅ CONCLUÍDA
- **T-17.1** — `log_acesso` em operações de escrita (middleware em `app/main.py` grava POST/PATCH/DELETE/PUT com usuário do token; login usa `app/services/log_acesso.py`)
- **T-17.2** — `log_auditoria` via código (não trigger): `app/services/auditoria.py` (`registrar_auditoria`/`auditar_escrita`) chamado nos CRUD de cursos, usuarios, trilhas, avaliacoes, badges, missoes, inscricoes — snapshot `dados_anteriores`/`dados_novos`
- **T-17.3/17.4** — `GET /auditoria/logs` com filtros (tabela, usuário, ação, período) + paginação
- **T-17.5** — exportação `formato=csv|pdf` dos logs
- **T-17.6** — 7 testes (`tests/test_us17.py`). RBAC `auditoria:visualizar` (admin + auditor)

### Issues 25-31 (ciclo de fixes 26/08-04/09) ✅ CONCLUÍDAS
- **25** — aulas ao vivo (11 pontos): código de acesso escondido (`_aula_read_para`), entrar valida inscrição+sem duplicar, silenciar por aula (`usuario_aula_silenciado`), acessar não grava presença, próximas por inscrição, X-Forwarded-For, token WS via subprotocolo, minhas-presencas, resumo do filtro, `saida_estimada`+presente por permanência mínima (migration `ad9d802fbf09`)
- **26** — Teams: aviso 422 quando `criar_reuniao_teams:true` e não configurado; **infra pendente** (4 vars `TEAMS_*` no deploy + Application Access Policy)
- **27** — WS da aula transmite presença (`_broadcast_presenca` entrou/saiu + `presenca_inicial` no accept)
- **28** — notificações: tabela `lms.notificacoes` + `app/services/notificacoes.py` + `GET /notificacoes`, `PATCH /{id}/lida`, `POST /marcar-todas-lidas`; disparo em aula agendada e gravação disponível
- **29** — login 500 ao cruzar critério de missão: recursão em `atribuir_xp`→`atualizar_progresso_missoes` corrigida com `checar_missoes=False` na recompensa
- **30** — fechada (falso positivo: rotas do dashboard eram da US-16)
- **31** — presença: `PresencaAula` é a fonte oficial; `sessoes/presenca` marcadas `deprecated=True` (legado)

### US-18: Integração End-to-End e Testes de Aceitação ✅ CONCLUÍDA
- **T-18.1** — Suíte completa: 35 arquivos (~305 testes). Relatório em `docs/us18-aceitacao.md`. Achados corrigidos: WebSocket (`TestClient` sync vs pytest-asyncio → novo `ws_client` ASGI async, 13 testes WS determinísticos) + certificado (`hash_validacao` na validacao publica).
- **T-18.2** — Carga 10k: `scripts/locustfile.py` (11 cenarios ponderados, headless `-u 10000 -r 50`, pool de credenciais) + `scripts/prepare_load_users.py`. Banco de teste reconciliado (`ad9d802fbf09` → `c7d3e9a1f204`); execucao real contra `localhost` (4 workers) com 20 usuarios: 0% falha, latencia medida.
- **T-18.3** — Seguranca: headers (X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy, Permissions-Policy), CI `bandit`+`safety`, corrigido XXE no SCORM (`defusedxml` em vez de `xml.etree`), 2 SQL injection nos seeds parametrizados. Bandit: 0 Medium/0 High.
- **T-18.4** — Acessibilidade WCAG: nao se aplica ao backend (API JSON); responsabilidade do frontend.
- **T-18.5** — LGPD: `log_acesso`/`log_auditoria` nao gravam CPF/senha/telefone; email/nome/IP minimos e necessarios (Art. 7º IX).
- **T-18.6** — Bugs corrigidos: WS loop, hash_validacao, XXE SCORM, SQL seeds.

## Próximas Prioridades (segundo ROADMAP.md)

- Estrutura Organizacional (estados, municípios, secretarias, unidades)
- Dashboards específicos por perfil (Gestor, Instrutor, Administrador Geral)
- Relatórios avançados (por município, secretaria, trilha)

**Backend core está praticamente completo:**
- ✅ Autenticação e credenciamento hierárquico
- ✅ Sistema RBAC (88 permissões)
- ✅ Trilhas de aprendizagem com progresso
- ✅ Cursos completos (módulos, unidades, aulas síncronas, chat)
- ✅ Upload de conteúdos multimídia (S3/local)
- ✅ SCORM completo
- ✅ Entregas de atividades
- ✅ Gamificação (badges, missões, níveis, leaderboard, streak)
- ✅ Progresso cascade (unidade → curso → trilha)
- ✅ Notificações (issue 28)
- ✅ Logs de auditoria (US-17)
- ✅ Certificados digitais (US-15)
- ✅ Dashboards/analytics (US-16)
- ✅ Integração Teams (opcional — requer infra)
- ✅ Recuperação de senha (SMTP config)
- ✅ Testes abrangentes (35 arquivos)
- ✅ Segurança (OWASP headers, bandit, XXE corrigido)
- ✅ Carga 10k (locust headless)
- ✅ LGPD auditada (US-18)

## T-06.10: Integração Teams + Artefato S3 (14/07/2026)

**Status:** Funcionalidades implementadas, aguardando Application Access Policy do Teams.

### O que foi implementado
- `app/services/storage.py` — `upload_bytes()` para upload de bytes crus (download de gravação)
- `app/services/teams.py` — `processar_gravacao()` (baixar Teams → S3 → criar Conteudo) e `sincronizar_presenca()` (lista de presença formatada)
- `app/api/cursos.py` — `POST /cursos/aulas/{id}/processar-gravacao` e `GET /cursos/aulas/{id}/presenca`
- `app/services/rbac.py` — Permissões `aula:processar_gravacao`, `aula:ver_presenca`
- `app/schemas/curso.py` — `gravacao_conteudo_id` nos schemas, `PresencaRegistroRead`, `ProcessarGravacaoResponse`
- `app/schemas/__init__.py` — (verificar se precisa atualizar)

### Para testar
1. Suporte executar PowerShell no Cloud Shell:
   ```powershell
   Connect-MicrosoftTeams
   New-CsApplicationAccessPolicy -Identity "LMS-Meeting-Policy" -AppIds "d8db36c7-bdda-4713-9048-59835c25e9da" -Description "Permite LMS criar reunioes Teams"
   Grant-CsApplicationAccessPolicy -PolicyName "LMS-Meeting-Policy" -Identity "gabriel.cicotoste@grupoge21.com"
   ```
2. Criar aula com `criar_reuniao_teams=true`
3. Após a aula, chamar `POST /cursos/aulas/{id}/processar-gravacao`

### Fluxo manual (sem policy)
- Professor cria reunião manualmente no Teams
- `POST /cursos/{id}/aulas` com `link_externo` = URL da reunião
- Após a aula, professor baixa MP4 do Stream e faz upload via `POST /conteudos/upload`
- Vincula com `PATCH /cursos/aulas/{id}` atualizando `gravacao_conteudo_id`

### Próximos passos sugeridos
- Upload direto de MP4 na tela da aula (frontend)
- Cron/polling para buscar gravação automaticamente
- Notificações para alunos sobre aulas agendadas
