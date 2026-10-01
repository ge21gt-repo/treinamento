# US-20 — Documentação e Entrega

> Relatório de entrega final com evidências de execução.
> Data: Outubro/2026 · Escopo: Backend LMS (FastAPI + SQLAlchemy async + PostgreSQL).

## 1. Resumo executivo

A plataforma de treinamento LMS foi entregue com o **backend completo**, cobrindo
as US-01 a US-19 (sprints anteriores) mais o ciclo de issues de lançamento #72-87
e a **integração Keycloak** (identidade única do IDESP), validada ponta a ponta
com o servidor real.

## 2. O que foi entregue

### 2.1 Funcionalidades

| Área | Entrega |
|---|---|
| Autenticação | Keycloak (JWT RS256/JWKS) + dual-mode com JWT local |
| RBAC | 6 perfis, ~88 permissões, hierarquia de aprovação |
| Credenciamento | Solicitações pendentes, aprovação/rejeição por superior |
| Cursos | CRUD cursos/módulos/unidades, reordenação, árvore, turma com nomes |
| Trilhas | CRUD, inscrição, progresso em cascata, inscritos |
| Conteúdo | Upload S3/local, chunk, player, SCORM seguro, materiais |
| Aulas síncronas | Aulas, chat, presença (fonte oficial), Teams (opcional) |
| Avaliações | Múltipla escolha + dissertativa, correção, estatísticas |
| Entregas | Upload de atividades, correção pelo instrutor |
| Chat/Fórum | SSE, WebSocket, moderação, termos bloqueados |
| Gamificação | Badges, missões, níveis, XP, leaderboard, streak |
| Certificados | PDF + QR + validação pública, emissão automática |
| Dashboard | KPIs, gráfico temporal, relatórios (CSV/PDF) |
| Auditoria | Logs de acesso e auditoria **imutável**, CSV/PDF |
| Notificações | Aulas agendadas, gravação disponível |

### 2.2 Documentação (T-20.1 a T-20.5)

| Artefato | Arquivo |
|---|---|
| Manual do administrador | `docs/manual-administrador.md` |
| Manual do instrutor | `docs/manual-instrutor.md` |
| Guia do participante | `docs/guia-participante.md` |
| Documentação técnica da API | Swagger/OpenAPI em `/docs` e `/redoc` |
| Este relatório | `docs/us20-entrega.md` |

## 3. Evidências de execução

### 3.1 Testes (T-18.1 / US-18)

- **35 arquivos de teste / ~305 testes**, cobrindo auth, RBAC, US-04..08,
  US-11..17, Keycloak e issues de lançamento.
- Ciclo #72-87: **73 testes passando** nos arquivos afetados (`test_trilhas`,
  `test_us16`, `test_us13`, `test_us17`, `test_certificados`,
  `test_mascarar_cpf`, `test_issue21_perfis`).

### 3.2 Carga (T-18.2)

- `scripts/locustfile.py`: 11 cenários ponderados, headless `-u 10000 -r 50`.
- Execução real contra `localhost` (4 workers, 20 usuários): **0% falha**.

### 3.3 Segurança (T-18.3)

- Headers OWASP (CSP, X-Frame-Options, X-Content-Type-Options, etc.).
- CI com `bandit` (0 Medium/High) e `safety`.
- XXE corrigido no SCORM (`defusedxml`); SQL injection nos seeds parametrizado.

### 3.4 LGPD (T-18.5)

- `log_acesso`/`log_auditoria` **não gravam** CPF/senha/telefone.
- `mascarar_cpf` nunca expõe CPF cru na validação pública.

### 3.5 Keycloak real (issue #71)

| Role | Perfil LMS | Validação real |
|---|---|---|
| `TRE_ADM` | `administrador_geral` | ✅ |
| `TRE_OPERADOR` | `administrador` | ✅ |
| `TRE_GESTOR` | `gestor` | ✅ |
| `TRE_INSTRUTOR` | `instrutor` | ✅ |
| `TRE_AUDITOR` | `auditor` | ✅ |
| `TRE_PARTICIPANTE` | `participante` (pendente→aprovado) | ✅ |

Testado ponta a ponta no ambiente dev com o Keycloak real do IDESP.

## 4. Ambiente e deploy

- **Branches**: `development` (dev), `homologacao` (hom), `main` (prod).
- **Deploy**: GitHub Actions → S3 → SSM → docker compose (EC2).
- **Health**: `GET /health` valida database, storage e migrations.
- **Head de migrations**: `179fc9c3ac09` (trigger de auditoria imutável).

## 5. Pendências de infraestrutura (acompanhamento)

| Item | Status |
|---|---|
| SMTP (`SMTP_*`) | Configurar para recuperação de senha |
| Teams (`TEAMS_*`) | Configurar + Application Access Policy |
| Vars `KEYCLOAK_*` no hom | Aplicar migration + vars no EC2 hom |
| Frontend (OIDC) | Equipe de front consumir a API |

## 6. Roteiro da sessão de handover (T-20.6)

Agenda sugerida (60 min):

1. **Arquitetura**: FastAPI + SQLAlchemy async + PostgreSQL (schema `lms`).
2. **Autenticação**: Keycloak real → RBAC → perfis `TRE_*`.
3. **Deploy**: fluxo GitHub Actions → S3 → SSM → docker compose; migrations.
4. **Monitoramento**: `GET /health` (DB, storage, migrations).
5. **Documentação**: manuais + Swagger (`/docs`) + ReDoc (`/redoc`).
6. **Pendências**: SMTP, Teams, vars Keycloak no hom, frontend.
7. **Próximos passos**: ROADMAP (estrutura organizacional, dashboards por perfil).