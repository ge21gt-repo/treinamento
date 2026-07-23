# Roadmap de Implementação — Backend LMS

## Progresso Geral

| Sprint | Foco | Período | Status |
|--------|------|---------|--------|
| **Sprint 1** | Estrutura Base (Auth, RBAC, Credenciamento) | S1 | ✅ 100% |
| **Sprint 2** | Cursos, Trilhas, Conteúdos, Progresso | S2 | ✅ 100% |
| **Sprint 3** | Avaliações (US-08) + Correções de segurança | S3 | ✅ 100% |
| **Sprint 4** | Pendências e Melhorias | Próximo | ⏳ 0% |

**43% concluído (31/72 tarefas)**

---

╔══════════════════════════════════════════════════════════════╗
║                   SPRINT 1 — ESTRUTURA BASE                  ║
║          Auth · RBAC · Credenciamento · 6 perfis            ║
╚══════════════════════════════════════════════════════════════╝

### Setup do Projeto
- [x] FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 (schema `lms`)
- [x] JWT (python-jose) + bcrypt (passlib)
- [x] Alembic async (5 migrations)
- [x] CORS configurável, `.env`, configurações multi-ambiente
- [x] Dockerfile + CI (GitHub Actions) + Fly.io deploy
- [x] Testes com PostgreSQL real + httpx.AsyncClient
- [x] Lifespan auto-migrate + seeds de perfis/níveis

### Autenticação e Cadastro
- [x] Registro com validação de campos únicos (email, CPF, telefone → 409)
- [x] Login com JWT
- [x] Recuperação de senha (esqueci-senha + redefinir-senha + email service)
- [x] LGPD (campo `aceite_lgpd` obrigatório)
- [x] 8 testes de autenticação

### RBAC — Controle de Acesso (US-03)
- [x] 6 perfis: `administrador_geral`, `administrador`, `instrutor`, `auditor`, `gestor`, `participante`
- [x] 38 permissões granulares (avaliação, curso, usuário, comentário, sandbox, etc.)
- [x] `require_permissao()` como dependency factory por endpoint
- [x] CRUD perfis completo (PATCH/DELETE)
- [x] Listar usuários por perfil
- [x] RBAC em `sessoes.py` e `comunicacao.py` — 14 endpoints protegidos
- [x] Proteção `POST /usuarios/perfis/atribuir` com `PERFIL_ATRIBUIR`
- [x] 10 testes RBAC

### Credenciamento Hierárquico
- [x] Hierarquia: `admin_geral` > `admin` > `instrutor` > `gestor` > `participante`
- [x] Registro cria solicitação pendente (status="pendente", usuário inativo)
- [x] `GET /credenciamento/solicitacoes/pendentes` com nome/e-mail
- [x] `POST /solicitacoes/{id}/aprovar` e `/rejeitar` com validação hierárquica
- [x] Tabela `aprovacoes_hierarquicas` para rastreabilidade
- [x] Sandbox do instrutor (`POST /sandbox/iniciar`, `/encerrar`, `/ativo`, `/sessoes`)
- [x] `scripts/criar_admin.py` para bootstrap do primeiro `admin_geral`

---

╔══════════════════════════════════════════════════════════════╗
║                  SPRINT 2 — CURSOS E CONTEÚDOS               ║
║       US-04 Trilhas · US-05 Cursos · US-06 Upload           ║
║               US-07 Progresso · SCORM · Teams               ║
╚══════════════════════════════════════════════════════════════╝

### US-04: Gestão de Trilhas
- [x] Model `InscricaoTrilha` (usuário, trilha, progresso, status)
- [x] `POST /trilhas/{id}/inscrever` — inscrição em trilha
- [x] `GET /trilhas/minhas-trilhas` — trilhas do usuário com progresso
- [x] `GET /trilhas/{id}/progresso` — progresso detalhado
- [x] Cálculo de progresso agregado (média dos cursos da trilha)
- [x] Permissões RBAC: `trilha:criar`, `editar`, `excluir`, `inscrever`, `ver_progresso`
- [x] Filtro por nível em `GET /trilhas`

### US-05: Gestão de Cursos, Módulos e Unidades
- [x] CRUD completo curso/módulo/unidade
- [x] Sub-módulos tipados: `conteudo_url`, `url_externa`
- [x] Aulas síncronas (CRUD + Teams integration + `GET /aulas/proximas`)
- [x] Chat contínuo por curso (POST/GET + SSE streaming)
- [x] Reordenação módulos/unidades (`PATCH /cursos/modulos/reorder`, `/unidades/reorder`)
- [x] Validação de pré-requisitos (existência, ciclo, bloqueio inscrição)
- [x] Árvore de conteúdo (`GET /cursos/{id}/arvore`)
- [x] XR (url_externa)
- [x] 11 testes

### US-06: Upload e Gestão de Conteúdos Multimídia
- [x] Serviço de upload S3 + local (streaming 8MB, sem dupla leitura)
- [x] Upload de vídeos, PDFs, áudio, imagens, SCORM
- [x] Materiais complementares por curso
- [x] Player de vídeo integrado + visualizador de PDF
- [x] Entrega de atividades (`EntregaAtividade`) + correção pelo instrutor
- [x] Suporte SCORM completo (PacoteScorm, TrackingScorm, launch, tracking, relatórios)
- [x] Upload chunked retomável: `POST /conteudos/upload/{iniciar, chunk, status, completar}`
- [x] RBAC: `conteudo:*`, `material:gerenciar`, `entrega:*`, `scorm:*`
- [x] Testes de upload, entregas e chunked upload

### US-07: Inscrição e Acompanhamento de Progresso
- [x] Serviço de progresso com cascade: unidade → curso → trilha
- [x] Verificação de duplicidade ao inscrever
- [x] `GET /cursos/inscricoes/minhas` — inscrições do próprio usuário
- [x] `DELETE /cursos/inscricoes/{id}` — cancelar inscrição
- [x] `POST /unidades/{id}/concluir` — marcar unidade como concluída
- [x] Dashboard pessoal: `GET /dashboard/meu-progresso`
- [x] Testes de rastreamento de progresso

---

╔══════════════════════════════════════════════════════════════╗
║               SPRINT 3 — AVALIAÇÕES E CORREÇÕES              ║
║      US-08 Avaliações · Paginação · Busca · Perfis JWT      ║
║       Validação unique · Multi-perfil · Segurança           ║
╚══════════════════════════════════════════════════════════════╝

### US-08: Sistema de Avaliações (issue #25)
- [x] CRUD avaliações (criar, listar, obter, atualizar, excluir)
- [x] CRUD questões (criar, listar, atualizar, excluir) + alternativas
- [x] Validação de tipos: `multipla_escolha`, `verdadeiro_falso`, `dissertativa`
- [x] `GET /{id}/responder` — obter avaliação para responder (sem gabarito)
- [x] `POST /{id}/submeter` — submeter respostas com cálculo de nota no servidor
- [x] Limite de tentativas + tempo limite (opcional)
- [x] Correção automática (alternativa correta → pontuação)
- [x] Feedback detalhado: `GET /{id}/resultado/{tentativa}`
- [x] Estatísticas: `GET /{id}/estatisticas`
- [x] Conclusão automática de unidade quando aprovado
- [x] RBAC: `avaliacao:criar`, `responder`, `editar`, `excluir`, `visualizar`
- [x] 235+ linhas de testes

### Correções de Infraestrutura
- [x] Test infrastructure: `pytest.ini` com `asyncio_default_test_loop_scope = session`
- [x] Raw ASGI middleware (removeu BaseHTTPMiddleware)
- [x] `db_clean` fixture com engine separada
- [x] `TEST_DATABASE_URL` isolado (database-2), `TEST_S3_BUCKET=lms-conteudos-teste`

### Fix #26 — Paginação sem X-Total-Count
- [x] 9 endpoints paginados retornam header `X-Total-Count`
- [x] Novo serviço `app/services/paginacao.py`
- [x] CORS expõe `X-Total-Count`

### Fix #27 — Busca por query string (ILIKE)
- [x] 7 endpoints aceitam `?q=...` para busca server-side
- [x] Helper `apply_search()` em `app/services/paginacao.py`

### Fix #21 — Perfis no UsuarioRead e JWT
- [x] `UsuarioRead` inclui campo `perfis: list[PerfilRead]`
- [x] JWT contém claim `perfis` para frontend

### Fix #22 — Validação de campos únicos
- [x] `check_unique_fields()` → retorna 409 com mensagem específica (email, CPF, telefone)

### Fix #23 — Unique constraint no telefone
- [x] `unique=True` no campo `telefone` do model Usuario
- [x] Migração Alembic `005_add_telefone_unique_constraint`

### Fix #28 — Nome/e-mail do solicitante no credenciamento
- [x] `usuario_nome` e `usuario_email` em `SolicitacaoCredenciamentoRead`

### Fix #29 — Criar usuário com perfil escolhido
- [x] `CriarSubordinadoRequest` com campo `perfil` + validação hierárquica

### Fix #31 — Achados críticos
- [x] Dupla leitura em upload eliminada (streaming 8MB)
- [x] RBAC adicionado em sessoes.py e comunicacao.py (14 endpoints)

### Fix #32 — Múltiplos perfis quebram require_permissao
- [x] `deps.py`: `scalar_one_or_none()` → `scalars().all()` + `any()`
- [x] `credenciamento.py`: mesmo fix em aprovar/rejeitar
- [x] Testado: RBAC 9/9, US-05 10/10, Issue21 6/6, validação manual ✅

### Fix #35 — DELETE /questoes/{id}
- [x] Novo endpoint `DELETE /questoes/{id}` com cascade nas alternativas
- [x] Protegido por `AVALIACAO_EXCLUIR`

### Fix #33 — Endpoints legados aceitavam nota/usuário forjados
- [x] `POST /respostas`: `usuario_id` forçado para `current_user.id`
- [x] `POST /resultados`: `usuario_id` forçado, `nota`/`aprovado` calculados server-side

### Fix #34 — Resultados visíveis para qualquer perfil
- [ ] **Pendente**

---

╔══════════════════════════════════════════════════════════════╗
║              SPRINT 4 — PENDÊNCIAS E PRÓXIMOS                ║
║       #34 · #24 · #30 · Estrutura · Dashboards             ║
╚══════════════════════════════════════════════════════════════╝

### 🔴 Críticas
- [ ] **#34** — Restringir `GET /resultados/{usuario_id}` e `GET /{id}/resultados` por perfil
- [ ] **#24** — Configurar SMTP real para envio de email de recuperação de senha
- [ ] **#30** — Isolamento de dados do Sandbox do Instrutor

### 🟢 Fáceis
- [ ] 4. Endpoint de horas de capacitação por usuário
- [ ] 5. Métricas de horas por órgão/instituição
- [ ] 6. Filtros por perfil no `/dashboard/resumo`
- [ ] 7. Relatório por servidor (cursos, progresso, horas)
- [ ] 8. Relatório por curso (inscritos, concluintes, média)
- [ ] 9. Exportação CSV nos relatórios

### 🟡 Médias — Estrutura Organizacional
- [ ] 10-17. Tabelas de estado/município/secretaria/unidade
- [ ] Vincular usuário à estrutura organizacional
- [ ] CRUD da estrutura organizacional
- [ ] Relacionamento gestor-funcionário

### 🟠 Médias-Altas — Controle de Acesso
- [ ] 27. Inscrição em curso exigir aprovação do gestor
- [ ] 28-30. Solicitação e aprovação de matrícula

### 🔴 Altas — Dashboards e Relatórios
- [ ] 31-38. Dashboards por perfil (Gestor, Instrutor, Admin Geral)
- [ ] Relatórios por município, secretaria, trilha
- [ ] Exportação PDF/XLSX

### 🔴 Muito Altas — Notificações
- [ ] 39-45. Sistema de notificações + integração com fluxos

### 🟣 Complexas — Integrações Externas
- [ ] 46-54. Módulo de integrações (provedores, webhooks, sincronização)

### 🟣 Extremamente Complexas — Arquitetura Avançada
- [ ] 55-58. Cache Redis, dashboards analíticos, busca avançada, relatórios dinâmicos

---

## Issues no GitHub

| # | Título | Status |
|---|--------|--------|
| **32** | Bug US-5 — Múltiplos perfis quebram require_permissao | ✅ Fix enviado |
| **35** | Gap funcional — DELETE /questoes/{id} | ✅ Fix enviado |
| **33** | Segurança — Endpoints legados aceitam nota/usuário forjados | ✅ Fix enviado |
| **34** | Privacidade — Resultados visíveis para qualquer perfil | ⏳ Pendente |
| **31** | Achados críticos do backend | ✅ Fechada |
| **30** | Isolamento Sandbox Instrutor | ⏳ Pendente |
| **29** | Criar usuário com perfil escolhido | ✅ Fechada |
| **28** | Nome/e-mail do solicitante no credenciamento | ✅ Fechada |
| **27** | Busca por query string | ✅ Fechada |
| **26** | Paginação sem X-Total-Count | ✅ Fechada |
| **25** | US-08: Sistema de Avaliações | ✅ Fechada |
| **24** | Configurar SMTP | ⏳ Pendente |
| **23** | Unique constraint telefone | ✅ Fechada |
| **22** | Validação campos únicos | ✅ Fechada |
| **21** | Perfis no JWT/UsuarioRead | ✅ Fechada |
| **18** | BUG: AmbiguousForeignKeysError | ✅ Fechada |

## Stack

```
Python 3.12 + FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15
JWT + bcrypt · S3/local · Teams API · SCORM
19 arquivos de teste · 1.600+ linhas · PostgreSQL real
```

---

## Arquitetura

```
app/
├── api/           # 12 módulos de rotas
├── models/        # 10+ models SQLAlchemy
├── schemas/       # Schemas Pydantic v2
├── services/      # 8 serviços de negócio
├── config.py      # Settings from .env
├── database.py    # Async engine + session factory
└── main.py        # Entrypoint com lifespan
```
