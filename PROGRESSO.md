# Progresso do Backend — Plataforma de Treinamento

---

## ✅ Sprint 1 — Estrutura Base (Auth + RBAC + Credenciamento)

**Setup:** FastAPI + SQLAlchemy async + PostgreSQL + JWT + Alembic + Docker + CI + Fly.io

**Autenticação:**
- Registro/login com JWT, hash bcrypt, validação de campos únicos (email, CPF, telefone → 409)
- Recuperação de senha (esqueci-senha + redefinir-senha + serviço de email)
- LGPD (aceite_lgpd obrigatório)

**RBAC (US-03):**
- 6 perfis: `administrador_geral`, `administrador`, `instrutor`, `auditor`, `gestor`, `participante`
- 38 permissões granulares mapeadas por perfil
- `require_permissao()` como dependency por endpoint
- CRUD de perfis, listar usuários por perfil
- RBAC protegendo 14 endpoints em sessoes.py e comunicacao.py
- `POST /usuarios/perfis/atribuir` protegido com `PERFIL_ATRIBUIR`

**Credenciamento Hierárquico:**
- Hierarquia: admin_geral > admin > instrutor > gestor > participante
- Registro cria solicitação pendente (usuário inativo até aprovação)
- Aprovação/rejeição com validação hierárquica
- Tabela `aprovacoes_hierarquicas` para rastreabilidade
- Sandbox do instrutor para testar avaliações

---

## ✅ Sprint 2 — Cursos, Trilhas, Conteúdos e Progresso

**US-04 Trilhas:**
- Inscrição em trilha, progresso agregado (média dos cursos)
- Minhas trilhas, progresso detalhado, filtro por nível

**US-05 Cursos:**
- CRUD curso/módulo/unidade, sub-módulos tipados (conteudo_url, url_externa)
- Aulas síncronas com integração Teams
- Chat contínuo por curso com SSE streaming
- Reordenação de módulos/unidades
- Validação de pré-requisitos (existência, ciclo, bloqueio)
- Árvore de conteúdo

**US-06 Upload:**
- Upload S3 + local (streaming 8MB, sem dupla leitura)
- Vídeos, PDFs, áudio, imagens, SCORM
- Materiais complementares, entrega de atividades com correção
- SCORM completo (PacoteScorm, TrackingScorm, launch, tracking, relatórios)
- Upload chunked retomável

**US-07 Progresso:**
- Cascade: unidade → curso → trilha
- Inscrição, cancelamento, conclusão de unidade
- Dashboard pessoal de progresso

---

## ⏳ Sprint 3 — Avaliações e Correções (parcial)

### ✅ Concluído

**US-08 — Sistema de Avaliações:**
- CRUD avaliações, questões e alternativas
- Tipos: múltipla_escolha, verdadeiro_falso, dissertativa
- Submeter com cálculo de nota no servidor
- Limite de tentativas, tempo limite, correção automática
- Feedback detalhado por questão
- Estatísticas da avaliação
- Conclusão automática de unidade quando aprovado

**Infraestrutura de Testes:**
- `pytest.ini` com `asyncio_default_test_loop_scope = session`
- Raw ASGI middleware (removeu BaseHTTPMiddleware)
- `db_clean` fixture com engine separada
- Database-2 isolado para testes, `TEST_S3_BUCKET` dedicado

**Issues Corrigidas:**
- #26 — Paginação com X-Total-Count (9 endpoints)
- #27 — Busca ILIKE por query string (7 endpoints)
- #21 — Perfis no UsuarioRead e JWT
- #22 — Validação de campos únicos antes do INSERT
- #23 — Unique constraint no telefone + migration
- #28 — Nome/e-mail do solicitante no credenciamento
- #29 — Criar usuário com perfil escolhido + script admin
- #31 — Achados críticos (dupla leitura upload, RBAC sessoes/comunicacao)
- #32 — Múltiplos perfis quebram require_permissao (branch fix)
- #35 — DELETE /questoes/{id} (branch fix)
- #33 — Endpoints legados aceitam nota/usuário forjados (branch fix)

### ⏳ Pendente

- **#34** — Restringir resultados de avaliação por perfil (privacidade)
- **#24** — Configurar SMTP real para email de recuperação
- **#30** — Isolamento de dados do Sandbox do Instrutor

---

## Próximas Entregas (Sprint 4+)

- Estrutura organizacional (estados, municípios, secretarias)
- Dashboards por perfil (Gestor, Instrutor, Admin)
- Relatórios (por município, secretaria, trilha)
- Sistema de notificações
- Integrações externas (webhooks, sincronização)

---

## Stack

```
Python 3.12 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 15
JWT · bcrypt · S3/local · Teams API · SCORM
19 arquivos de teste · 1.600+ linhas
```
