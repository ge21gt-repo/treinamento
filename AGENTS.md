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

- **Tests:** 19 test files with 1,600+ lines covering auth, RBAC, US-04/05/06/07, bug fixes, and other modules. Run with `pytest`.
- **Test Database:** Uses `TEST_DATABASE_URL` (database-2, senha separada) — isolado do dev. Bucket S3 de teste: `lms-conteudos-teste`.
- **Test infrastructure:** `pytest.ini` uses `asyncio_default_test_loop_scope = session`. Raw ASGI middleware (no BaseHTTPMiddleware). `db_clean` fixture uses separate engine to avoid pool corruption. `event_loop` fixture is session-scoped. Tests override `STORAGE_BACKEND=local`.
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

- **Branch:** `devin/1782154515-backend-lms` (development branch)
- **Current work branch:** `fix/paginacao-e-busca` (issues #26/#27 — not yet merged)
- **Production Branch:** `main` (PR → deploy)
- **Roadmap:** 31/72 tasks done (43%). US-04 ✅, US-05 ✅, US-06 ✅, US-07 ✅, Pendências Técnicas ✅, Issues #21/#22/#23 ✅.
- **Next up:** US-08 (Sistema de Avaliações — issue #25)
- **Known issues:** SMTP não configurado (#24) — `esqueci-senha` não envia emails
- **Previous milestones:** Credenciamento flow (tasks 18-26), RBAC (tasks 17.2-17.3, 30.1), US-04 (Trilhas), US-05 (Cursos avançado), US-06 (Upload S3/Conteúdos), US-07 (Progresso cascade).
- **Structure of Courses & Trails:** FULLY IMPLEMENTED (TrilhaAprendizagem, Curso, Modulo, Unidade, Inscricao, ProgressoUnidade, InscricaoTrilha, MensagemCurso, AulaSincrona)
- **Endpoints for Trails:** FULLY IMPLEMENTED (GET/POST/PATCH/DELETE /api/v1/trilhas + inscrever/progresso/minhas-trilhas)
- **Endpoints for Courses:** FULLY IMPLEMENTED (complete CRUD for cursos, modulos, unidades, inscricoes, progresso, aulas, chat, consumo, arvore)
- **Storage:** S3 (aioboto3) or local disk for uploads (videos, PDFs, SCORM, materials, deliveries)
- **Teams Integration:** Microsoft Graph API for synchronous classes (optional, fallback to manual links)
- **SCORM Support:** Complete implementation (PacoteScorm, TrackingScorm, launch, tracking, reports)
- **5 Alembic migrations** exist: from `001_add_credenciamento_fields` to `005_add_telefone_unique_constraint`. Chain new ones with `down_revision` pointing to `'005_add_telefone_unique_constraint'`.
- **`scripts/init_db.sql`** creates the `lms` schema, extensions (`pgcrypto`, `citext`), seeds profiles/niveis, and adds performance indexes — it is idempotent (uses `ON CONFLICT DO NOTHING`).

## Convictions

- **Testar o boot da app localmente antes de qualquer merge é obrigatório** — rodar o `lifespan`/start (ex.: `async with lifespan(app)`) para validar create_all + seeds. Incidente 14/08: seed sem coluna NOT NULL crashava o start e derrubou hom/dev (502).
- **Seed via SQL puro: TODAS as colunas NOT NULL explícitas** — o default do model SQLAlchemy não vale em `INSERT` via `text()`; sem isso o start crasha com `NotNullViolationError`.
- Always add imports in `__init__.py` for new models/schemas.
- Chain new migrations with `down_revision` pointing to latest migration (currently `'005_add_telefone_unique_constraint'`).
- Use Pydantic v2 style (no `orm_mode`, use `model_config`).
- SQLAlchemy 2.0 style — use `select()`, `await db.execute()`, no `Query` API.
- Run tests with `pytest` before major changes — 19 test files with 1,600+ lines of coverage.
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

## Próximas Prioridades (segundo ROADMAP.md)

- Estrutura Organizacional (estados, municípios, secretarias, unidades)
- Dashboards específicos por perfil (Gestor, Instrutor, Administrador Geral)
- Relatórios avançados (por município, secretaria, trilha)
- Sistema de notificações

**Backend core está praticamente completo:**
- ✅ Autenticação e credenciamento hierárquico
- ✅ Sistema RBAC com 38 permissões
- ✅ Trilhas de aprendizagem com progresso
- ✅ Cursos completos (módulos, unidades, aulas síncronas, chat)
- ✅ Upload de conteúdos multimídia (S3/local)
- ✅ SCORM completo
- ✅ Entregas de atividades
- ✅ Gamificação básica
- ✅ Progresso cascade (unidade → curso → trilha)
- ✅ Integração Teams (opcional)
- ✅ Recuperação de senha
- ✅ Testes abrangentes (19 arquivos, 1.600+ linhas)

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
