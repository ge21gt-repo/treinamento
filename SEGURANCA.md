# Raio-X de Segurança — Backend LMS

> Data: 23/07/2026
> Branch: `fix/issues-34-35-multiplos-perfis`

---

## ✅ Corrigidos (branch `fix/issues-34-35-multiplos-perfis`)

| # | Arquivo | Problema | Correção |
|---|---------|----------|----------|
| #32 | `app/api/deps.py` + `app/services/credenciamento.py` | `require_permissao` usava `scalar_one_or_none()` — só validava 1 perfil. Usuário com múltiplos perfis (ex: gestor + instrutor) quebrava autorização. `credenciamento.py` tinha o mesmo bug em aprovar/rejeitar. | `scalars().all()` + `any(has_permission(...))` |
| #35 | `app/api/avaliacoes.py` | Não existia `DELETE /questoes/{id}` | Endpoint adicionado (204/404/403) com cascade nas alternativas |
| #33 | `app/api/avaliacoes.py` | `POST /respostas` aceitava `usuario_id` do cliente — qualquer um podia postar como outro. `POST /resultados` aceitava `nota` e `aprovado` — qualquer um podia forjar nota 100. | `usuario_id` forçado para `current_user.id`. `nota` e `aprovado` calculados server-side (busca respostas reais do usuário e recalcula) |
| #34 | `app/api/avaliacoes.py` + `app/services/rbac.py` | `GET /{avaliacao_id}/resultados` e `GET /resultados/{usuario_id}` expunham resultados de QUALQUER usuário para QUALQUER perfil autenticado | Nova permissão `AVALIACAO_AVALIAR`. Admin/instrutor vê todos. Participante vê só próprios. Ver outro usuário → 403 sem permissão |

---

## 🔴 84 Endpoints sem `require_permissao` (só `get_current_user`)

### 1. `app/api/usuarios.py` — 9 endpoints críticos

| Rota | Método | Risco |
|------|--------|-------|
| `/usuarios` | GET | Qualquer logado lista todos os usuários |
| `/usuarios/{usuario_id}` | GET | Qualquer logado vê qualquer usuário |
| `/usuarios/{usuario_id}` | PATCH | **Qualquer logado edita qualquer usuário** |
| `/usuarios/{usuario_id}` | DELETE | **Qualquer logado deleta qualquer usuário** |
| `/usuarios/perfis/todos` | GET | Lista todos os perfis do sistema |
| `/usuarios/perfis` | POST | **Qualquer logado cria perfil novo** |
| `/usuarios/perfis/{perfil_id}` | PATCH | **Qualquer logado edita perfil** |
| `/usuarios/perfis/{perfil_id}` | DELETE | **Qualquer logado deleta perfil** |
| `/usuarios/criar-subordinado` | POST | Cria subordinado (só valida hierarquia, sem RBAC) |

**Único protegido:** `POST /usuarios/perfis/atribuir` ✅ (`require_permissao(PERFIL_ATRIBUIR)`)

---

### 2. `app/api/cursos.py` — 27 endpoints críticos

| Rota | Método | Risco |
|------|--------|-------|
| `/cursos` | GET | Lista cursos |
| `/cursos` | **POST** | **Qualquer logado cria curso** |
| `/cursos/{curso_id}` | GET | Vê curso |
| `/cursos/{curso_id}` | **PATCH** | **Qualquer logado edita qualquer curso** |
| `/cursos/{curso_id}` | **DELETE** | **Qualquer logado deleta qualquer curso** |
| `/cursos/{curso_id}/arvore` | GET | Vê árvore |
| `/cursos/{curso_id}/modulos` | GET | Lista módulos |
| `/cursos/modulos` | **POST** | **Qualquer logado cria módulo** |
| `/cursos/modulos/reorder` | **PATCH** | **Qualquer logado reordena módulos** |
| `/cursos/modulos/{modulo_id}` | **PATCH** | **Qualquer logado edita módulo** |
| `/cursos/modulos/{modulo_id}` | **DELETE** | **Qualquer logado deleta módulo** |
| `/cursos/modulos/{modulo_id}/unidades` | GET | Lista unidades |
| `/cursos/unidades` | **POST** | **Qualquer logado cria unidade** |
| `/cursos/unidades/reorder` | **PATCH** | **Qualquer logado reordena unidades** |
| `/cursos/unidades/{unidade_id}` | **PATCH** | **Qualquer logado edita unidade** |
| `/cursos/unidades/{unidade_id}` | **DELETE** | **Qualquer logado deleta unidade** |
| `/cursos/{curso_id}/aulas` | GET | Lista aulas |
| `/cursos/{curso_id}/aulas` | **POST** | **Qualquer logado cria aula síncrona** |
| `/cursos/aulas/proximas` | GET | Próximas aulas (dados próprios) |
| `/cursos/aulas/{aula_id}` | **PATCH** | **Qualquer logado edita aula** |
| `/cursos/aulas/{aula_id}` | **DELETE** | **Qualquer logado deleta aula** |
| `/cursos/{curso_id}/chat/stream` | GET | SSE stream |
| `/cursos/{curso_id}/chat` | GET | Lista chat |
| `/cursos/{curso_id}/chat` | **POST** | **Qualquer logado envia chat** |
| `/cursos/inscricoes/{usuario_id}` | GET | **Vê inscrições de qualquer usuário** |
| `/cursos/progresso` | **POST** | **Cria progresso para qualquer um** |
| `/cursos/progresso/{progresso_id}` | **PATCH** | **Edita progresso de qualquer um** |

**Protegidos:** `POST /inscricoes` ✅, `GET /inscricoes/minhas` ✅, `DELETE /inscricoes/{id}` ✅, `POST /unidades/{id}/concluir` ✅, `GET /{id}/consumo` ✅, `POST /aulas/{id}/processar-gravacao` ✅, `GET /aulas/{id}/presenca` ✅

---

### 3. `app/api/trilhas.py` — 6 endpoints

| Rota | Método | Risco |
|------|--------|-------|
| `/trilhas` | GET | Lista trilhas |
| `/trilhas` | **POST** | **Qualquer logado cria trilha** |
| `/trilhas/minhas-trilhas` | GET | Próprias trilhas (dados próprios) |
| `/trilhas/{trilha_id}` | GET | Vê trilha |
| `/trilhas/{trilha_id}` | **PATCH** | **Qualquer logado edita qualquer trilha** |
| `/trilhas/{trilha_id}` | **DELETE** | **Qualquer logado deleta qualquer trilha** |

**Protegidos:** `GET /{id}/progresso` ✅, `POST /{id}/inscrever` ✅, `GET /{id}/progresso-detalhado` ✅

---

### 4. `app/api/dashboard.py` — 4 endpoints

| Rota | Método | Risco |
|------|--------|-------|
| `/dashboard/resumo` | GET | **Qualquer logado vê métricas do sistema (total usuários, cursos...)** |
| `/dashboard/meu-progresso` | GET | ✅ Só próprio |
| `/dashboard/metricas/{usuario_id}` | GET | **Qualquer logado vê métricas de qualquer usuário** |
| `/dashboard/logs` | GET | **Qualquer logado vê logs de acesso do sistema** |
| `/dashboard/cursos/{curso_id}/stats` | GET | **Qualquer logado vê estatísticas de qualquer curso** |

---

### 5. `app/api/certificados.py` — 5 endpoints

| Rota | Método | Risco |
|------|--------|-------|
| `/certificados/modelos` | GET | Lista modelos |
| `/certificados/modelos` | **POST** | **Qualquer logado cria modelo de certificado** |
| `/certificados` | **POST** | **Qualquer logado emite certificado para QUALQUER usuário** |
| `/certificados/{certificado_id}` | GET | Vê certificado |
| `/certificados/usuario/{usuario_id}` | GET | **Qualquer logado vê certificados de qualquer um** |

---

### 6. `app/api/gamificacao.py` — 16 endpoints

| Rota | Método | Risco |
|------|--------|-------|
| `/gamificacao/niveis` | GET | Lista níveis |
| `/gamificacao/niveis` | **POST** | **Qualquer logado cria nível** |
| `/gamificacao/xp` | **POST** | **Qualquer logado adiciona XP a QUALQUER usuário** |
| `/gamificacao/xp/{usuario_id}` | GET | Vê XP de qualquer um |
| `/gamificacao/xp/{usuario_id}/total` | GET | Vê total de XP de qualquer um |
| `/gamificacao/leaderboard` | GET | Leaderboard |
| `/gamificacao/badges` | GET | Lista badges |
| `/gamificacao/badges` | **POST** | **Qualquer logado cria badge** |
| `/gamificacao/badges/atribuir` | **POST** | **Qualquer logado atribui badge a QUALQUER usuário** |
| `/gamificacao/badges/{usuario_id}` | GET | Vê badges de qualquer um |
| `/gamificacao/missoes` | GET | Lista missões |
| `/gamificacao/missoes` | **POST** | **Qualquer logado cria missão** |
| `/gamificacao/missoes/{missao_id}` | **PATCH** | **Qualquer logado edita missão** |
| `/gamificacao/missoes/participar` | POST | Participa de missão |
| `/gamificacao/missoes/usuario/{usuario_missao_id}` | **PATCH** | **Qualquer logado edita progresso de missão de qualquer um** |
| `/gamificacao/streaks/{usuario_id}` | GET | Vê streak de qualquer um |

---

### 7. `app/api/credenciamento.py` — 3 endpoints

| Rota | Método | Risco |
|------|--------|-------|
| `/credenciamento/solicitacoes/pendentes` | GET | **Qualquer logado vê TODAS as solicitações pendentes** |
| `/credenciamento/solicitacoes/{id}/aprovar` | POST | **Qualquer logado pode chamar** (mas service valida hierarquia antes de aprovar) |
| `/credenciamento/solicitacoes/{id}/rejeitar` | POST | **Qualquer logado pode chamar** (mas service valida hierarquia antes de rejeitar) |

---

## 🟡 Problemas de Fluxo e Validação

### 8. `POST /auth/registro` — Não gera solicitação (PRECISA CORRIGIR)
- **Arquivo:** `app/api/auth.py:48-81`
- **Problema:** Cria usuário `ativo=True` direto, sem `SolicitacaoCredenciamento`. Perfil é `participante` fixo. Usuário já nasce ativo sem aprovação de ninguém.
- **Impacto:** Qualquer pessoa se cadastra como participante ativo e acessa o sistema imediatamente — o fluxo de credenciamento é completamente ignorado.
- **Correção necessária:** Seguir o mesmo padrão do `registro-com-perfil` — criar solicitação pendente, usuário inativo.

### 9. `POST /auth/registro-com-perfil` — Já gera solicitação ✅ (mas sem validação de perfil permitido)
- **Arquivo:** `app/api/auth.py:84-105`
- **Problema:** Qualquer pessoa pode solicitar qualquer perfil (`administrador_geral`, `instrutor`, `gestor`, `participante`). Não valida se o perfil solicitado pode ser auto-solicitado via registro público.
- **Impacto:** Alguém pode solicitar `administrador_geral` diretamente. A aprovação ainda depende de admin_geral aprovar, mas expõe opções desnecessárias.
- **Correção sugerida:** Restringir perfis auto-solicitáveis via registro público (ex: só `participante` e talvez `gestor`). Remover `administrador_geral` da lista.

### 10. `POST /usuarios/criar-subordinado` — Não gera solicitação (PRECISA CORRIGIR POR DECISÃO)
- **Arquivo:** `app/api/usuarios.py:189-239`
- **Problema:** Cria usuário ativo com `status_credenciamento="aprovado"` e `criado_por=current_user.id`, mas **não cria registro de `SolicitacaoCredenciamento`**. Também **não tem campo `data_aceite_lgpd`** no schema nem na criação.
- **Decisão do usuário:** Adicionar `SolicitacaoCredenciamento` (status "aprovado", avaliado_por=current_user.id) + `AprovacaoHierarquica` para manter trilha de auditoria. Adicionar campo `data_aceite_lgpd`.
- **Correção necessária:**
  1. Adicionar `aceite_lgpd: bool` ao `CriarSubordinadoRequest`
  2. Adicionar `data_aceite_lgpd` ao criar usuário
  3. Criar `SolicitacaoCredenciamento` com status "aprovado"
  4. Criar `AprovacaoHierarquica` registrando o aprovador

### 11. Perfil `instrutor` sem `CREDENCIAMENTO_LISTAR` e `CREDENCIAMENTO_APROVAR`
- **Arquivo:** `app/services/rbac.py`
- **Problema:** O service `credenciamento.py` já valida que instrutor pode aprovar `gestor` e `participante` pela hierarquia. Mas as permissões RBAC `CREDENCIAMENTO_LISTAR` e `CREDENCIAMENTO_APROVAR` **não existem** no mapeamento `PERFIL_PERMISSOES`.
- **Impacto:** Instrutor consegue aprovar chamando a rota direto (o service permite), mas **não consegue listar pendentes** via endpoint oficial se colocarmos `require_permissao(CREDENCIAMENTO_LISTAR)`. Também não conseguirá aprovar se adicionarmos `require_permissao(CREDENCIAMENTO_APROVAR)` sem mapear para instrutor.
- **Correção necessária:** Adicionar as permissões no `rbac.py` e mapear para os perfis corretos.

---

## ⏳ Pendências Conhecidas

| # | Problema | Arquivo | Impacto |
|---|----------|---------|---------|
| #24 | SMTP não configurado | `app/services/email.py` | Recuperação de senha não envia email |
| #30 | Sandbox não isola dados reais | `app/api/sandbox.py` | Instrutor pode afetar dados reais durante testes |

---

## ✅ Totalmente Protegidos (com `require_permissao`)

| Arquivo | Endpoints | Status |
|---------|-----------|--------|
| `app/api/avaliacoes.py` | 22 | ✅ `AVALIACAO_*` |
| `app/api/conteudos.py` | 16 | ✅ `CONTEUDO_*`, `MATERIAL_GERENCIAR` |
| `app/api/entregas.py` | 6 | ✅ `ENTREGA_*` |
| `app/api/scorm.py` | 5 | ✅ `SCORM_*` |
| `app/api/sessoes.py` | 8 | ✅ `SESSAO_*` |
| `app/api/comunicacao.py` | 9 | ✅ `CHAT_*`, `FORUM_*` |
| `app/api/sandbox.py` | 2 | ✅ `SANDBOX_TESTAR` (iniciar/encerrar) |

**Total protegido: 68 endpoints**

---

## Resumo Final

| Categoria | Quantidade |
|-----------|-----------|
| ✅ Endpoints protegidos (RBAC) | 68 |
| 🔴 Endpoints sem RBAC | 84 |
| 🔴 Problemas de fluxo (registro, permissões) | 4 |
| ⏳ Pendências conhecidas (#24, #30) | 2 |
| **Total de problemas identificados** | **90** |

---

## Correções já decididas pelo usuário (pendentes de implementação)

1. **`auth/registro`**: Unificar com `registro-com-perfil` — criar solicitação pendente, usuário inativo (perfil fixo `participante`)
2. **`criar-subordinado`**: Adicionar `SolicitacaoCredenciamento` (status "aprovado") + `AprovacaoHierarquica` + campo `aceite_lgpd`/`data_aceite_lgpd`
3. **`credenciamento.py` (listar/aprovar/rejeitar)**: Adicionar `require_permissao(CREDENCIAMENTO_LISTAR)` e `(CREDENCIAMENTO_APROVAR)`; mapear as permissões para admin_geral, admin e instrutor
4. **84 endpoints sem RBAC**: Aguardando definição de prioridades
