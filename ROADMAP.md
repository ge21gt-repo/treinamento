# Roadmap de Implementação - Plataforma de Capacitação Governamental

## Progresso Geral

| Sprint | Foco | Status |
|--------|------|--------|
| **Sprint 1** | Estrutura Base (Auth, RBAC, Credenciamento) | ✅ 100% |
| **Sprint 2** | Cursos, Trilhas, Conteúdos, Progresso (US-04/05/06/07) | ✅ 100% |
| **Sprint 3** | Avaliações (US-08) + Correções de segurança | ✅ 100% |
| **Sprint 4** | Pendências e Melhorias | ⏳ 0% |

---

## ✅ Sprint 1 — Estrutura Base

### Setup (antes das USs)
- [x] FastAPI + SQLAlchemy async + PostgreSQL (schema `lms`)
- [x] JWT (python-jose) + bcrypt (passlib)
- [x] Alembic async (5 migrations)
- [x] CORS configurável, `.env`, configurações por ambiente
- [x] Dockerfile + CI (GitHub Actions) + Fly.io deploy
- [x] Testes com PostgreSQL real + httpx.AsyncClient
- [x] Lifespan auto-migrate + seeds de perfis/níveis

### US-02: Autenticação e Cadastro
- [x] Registro com validação de campos únicos (email, CPF, telefone) → 409
- [x] Login com JWT
- [x] Recuperação de senha (esqueci-senha + redefinir-senha + email service)
- [x] LGPD (campo `aceite_lgpd` obrigatório)
- [x] 8 testes de autenticação

### US-03: RBAC + Perfis
- [x] 6 perfis: `administrador_geral`, `administrador`, `instrutor`, `auditor`, `gestor`, `participante`
- [x] 38 permissões granulares (avaliação, curso, usuário, comentário, sandbox, etc.)
- [x] `require_permissao()` como dependency factory por endpoint
- [x] CRUD perfis completo (PATCH/DELETE)
- [x] Listar usuários por perfil
- [x] RBAC em **sessoes.py** e **comunicacao.py** — 14 endpoints protegidos
- [x] Proteção `POST /usuarios/perfis/atribuir` com `PERFIL_ATRIBUIR`
- [x] 10 testes RBAC

### Credenciamento Hierárquico
- [x] Hierarquia: `admin_geral` > `admin` > `instrutor` > `gestor` > `participante`
- [x] Registro cria solicitação pendente (status="pendente", usuário inativo)
- [x] `GET /credenciamento/solicitacoes/pendentes` — lista solicitações com nome/e-mail do solicitante
- [x] `POST /solicitacoes/{id}/aprovar` e `/rejeitar` — validação hierárquica
- [x] Tabela `aprovacoes_hierarquicas` para rastreabilidade
- [x] Sandbox do instrutor (`POST /sandbox/iniciar`, `/encerrar`, `/ativo`, `/sessoes`)

---

## ✅ Sprint 2 — Cursos, Trilhas, Conteúdos e Progresso

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
- [x] **Upload chunked retomável**: `POST /conteudos/upload/{iniciar, chunk, status, completar}`
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

## ✅ Sprint 3 — US-08: Sistema de Avaliações + Correções

### US-08: Avaliações (issue #25)
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

### Correções de Segurança e Bugs

#### Fix #26 — Paginação sem X-Total-Count
- [x] 9 endpoints paginados retornam header `X-Total-Count`
- [x] Novo serviço `app/services/paginacao.py`
- [x] CORS expõe `X-Total-Count`

#### Fix #27 — Busca por query string (ILIKE)
- [x] 7 endpoints aceitam `?q=...` para busca server-side
- [x] `apply_search()` helper em `app/services/paginacao.py`

#### Fix #21 — Perfis no UsuarioRead e JWT
- [x] `UsuarioRead` inclui campo `perfis: list[PerfilRead]`
- [x] JWT contém claim `perfis` para frontend

#### Fix #22 — Validação de campos únicos antes do INSERT
- [x] `check_unique_fields()` → retorna 409 com mensagem específica

#### Fix #23 — Unique constraint no telefone
- [x] `unique=True` no campo `telefone` do model Usuario
- [x] Migração Alembic `005_add_telefone_unique_constraint`

#### Fix #28 — Nome/e-mail do solicitante no credenciamento
- [x] `usuario_nome` e `usuario_email` em `SolicitacaoCredenciamentoRead`

#### Fix #29 — Criar usuário com perfil escolhido
- [x] `CriarSubordinadoRequest` com campo `perfil`
- [x] `scripts/criar_admin.py` para bootstrap do primeiro `admin_geral`

#### Fix #31 — Achados críticos do backend
- [x] Dupla leitura em upload eliminada (streaming 8MB)
- [x] RBAC em sessoes.py e comunicacao.py

## ✅ Sprint 3.5 — Correções em andamento (branch `fix/issues-34-35-multiplos-perfis`)

### Fix #32 — Múltiplos perfis quebram require_permissao
- [x] `require_permissao` em `deps.py`: `scalar_one_or_none()` → `scalars().all()` + `any()`
- [x] `credenciamento.py`: mesmo fix em `aprovar_solicitacao` e `rejeitar_solicitacao`
- [x] Testado: RBAC 9/9, US-05 10/10, Issue21 6/6, validação manual ✅

### Fix #35 — DELETE /questoes/{id}
- [x] Novo endpoint `DELETE /questoes/{id}` com cascade nas alternativas
- [x] Protegido por `AVALIACAO_EXCLUIR`

### Fix #33 — Endpoints legados aceitam nota/usuário forjados
- [x] `POST /respostas`: `usuario_id` forçado para `current_user.id`
- [x] `POST /resultados`: `usuario_id` forçado, `nota`/`aprovado` calculados server-side

### Fix #34 — Resultados visíveis para qualquer perfil
- [ ] Pendente

---

## ⏳ Sprint 4 — Pendências e Próximos Passos

### 🔴 Críticas
- [ ] **#34** — Restringir `GET /resultados/{usuario_id}` e `GET /{id}/resultados` por perfil
- [ ] **#24** — Configurar SMTP real para envio de email de recuperação de senha
- [ ] **#30** — Isolamento de dados do Sandbox do Instrutor

### 🟢 Fáceis
- [ ] 4. Implementar endpoint de horas de capacitação por usuário
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
- [ ] Gestor listar subordinados

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

## Estatísticas

- **Total de tarefas (ROADMAP original)**: 72
- **Concluídas**: 31 (todas as US + 10 issues de correção)
- **Pendentes**: 41
- **Progresso**: 43%

## Issues no GitHub

| # | Título | Status |
|---|--------|--------|
| 32 | Bug US-5 — Múltiplos perfis quebram require_permissao | ✅ Fix enviado |
| 35 | Gap funcional — DELETE /questoes/{id} | ✅ Fix enviado |
| 33 | Segurança — Endpoints legados aceitam nota/usuário forjados | ✅ Fix enviado |
| 34 | Privacidade — Resultados visíveis para qualquer perfil | ⏳ Pendente |
| 31 | Achados críticos do backend | ✅ Fechada |
| 30 | Isolamento Sandbox Instrutor | ⏳ Pendente |
| 29 | Criar usuário com perfil escolhido | ✅ Fechada |
| 28 | Nome/e-mail do solicitante no credenciamento | ✅ Fechada |
| 27 | Busca por query string | ✅ Fechada |
| 26 | Paginação sem X-Total-Count | ✅ Fechada |
| 25 | US-08: Sistema de Avaliações | ✅ Fechada |
| 24 | Configurar SMTP | ⏳ Pendente |
| 23 | Unique constraint telefone | ✅ Fechada |
| 22 | Validação campos únicos | ✅ Fechada |
| 21 | Perfis no JWT/UsuarioRead | ✅ Fechada |
| 18 | BUG: AmbiguousForeignKeysError | ✅ Fechada |

## Arquitetura do Projeto

```
app/
├── api/           # 12 módulos de rotas (auth, cursos, trilhas, avaliacoes, etc.)
├── models/        # 10+ models SQLAlchemy
├── schemas/       # Schemas Pydantic v2
├── services/      # 8 serviços (auth, rbac, progresso, storage, avaliacao, etc.)
├── config.py      # Settings from .env
├── database.py    # Async engine + session factory
└── main.py        # App entrypoint com lifespan
```

**Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 + JWT + S3/local + Teams API

**Testes:** 19 arquivos, 1.600+ linhas, PostgreSQL real, httpx.AsyncClient
