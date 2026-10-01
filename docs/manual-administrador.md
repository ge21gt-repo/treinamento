# Manual do Administrador — Plataforma de Treinamento LMS

> US-20 / T-20.1 — Documentação baseada na API real do backend (v1).

## 1. Visão geral do papel

O **administrador** é o perfil com maior nível de acesso à plataforma. Ele é
responsável por:

- Gerenciar usuários e o processo de **credenciamento** (aprovação de acesso)
- Gerenciar **perfis e permissões** (RBAC)
- Acompanhar **relatórios e dashboards** de desempenho
- Gerenciar cursos, trilhas, avaliações e conteúdos
- Consultar **logs de auditoria** e exportar relatórios
- Emitir e gerenciar **certificados**

Existem dois níveis administrativos:

| Perfil | Permissões | Diferença |
|---|---|---|
| `administrador_geral` | 87 permissões | Acesso total, inclui auditoria + todos os dashboards |
| `administrador` | 83 permissões | Igual ao geral, **menos** auditoria e dashboards de KPIs/gráficos/relatórios |

## 2. Acesso e autenticação

O login é feito via **Keycloak** (identidade única do IDESP). O backend valida o
token JWT (RS256) contra o realm `idesp-realm` e mapeia as roles `TRE_*` para os
perfis internos:

| Role Keycloak | Perfil LMS |
|---|---|
| `TRE_ADM` | `administrador_geral` |
| `TRE_OPERADOR` | `administrador` |
| `TRE_GESTOR` | `gestor` |
| `TRE_INSTRUTOR` | `instrutor` |
| `TRE_AUDITOR` | `auditor` |
| `TRE_PARTICIPANTE` | `participante` |

> A atribuição das roles `TRE_*` aos usuários é feita no Keycloak (console de
> administração do IDESP), **não** no backend.

## 3. Gestão de usuários

Endpoints: `/api/v1/usuarios`

| Operação | Endpoint | Observação |
|---|---|---|
| Listar usuários | `GET /usuarios` | Paginado, busca por `?q=`, filtro por `?perfil=` |
| Ver usuário | `GET /usuarios/{id}` | Inclui perfis |
| Atualizar usuário | `PATCH /usuarios/{id}` | Edita dados cadastrais |
| Excluir usuário | `DELETE /usuarios/{id}` | Remove o registro |
| Ver dados próprios | `GET /usuarios/me` | Perfil autenticado |
| Criar subordinado | `POST /usuarios/criar-subordinado` | Gestor cria contas de participante |
| Gerenciar perfis | `POST/PATCH/DELETE /usuarios/perfis` | CRUD de perfis RBAC |
| Atribuir perfil | `POST /usuarios/perfis/atribuir` | Vincula perfil a usuário |

## 4. Credenciamento (aprovação de acesso)

Endpoints: `/api/v1/credenciamento`

| Operação | Endpoint |
|---|---|
| Listar solicitações pendentes | `GET /credenciamento/solicitacoes/pendentes` |
| Aprovar solicitação | `POST /credenciamento/solicitacoes/{id}/aprovar` |
| Rejeitar solicitação | `POST /credenciamento/solicitacoes/{id}/rejeitar` |

**Fluxo:**

1. Um novo usuário se cadastra (ou provisiona via Keycloak).
2. O backend cria uma solicitação com `status="pendente"` e o usuário fica **inativo**.
3. O administrador analisa a solicitação e **aprova** (usuário ativa) ou **rejeita**.
4. Usuários de perfis de gestão (roles `TRE_ADM`/`TRE_GESTOR`/etc.) nascem **aprovados** automaticamente.

> Perfis de gestão aprovam usuários de níveis inferiores (hierarquia):
> `administrador_geral` > `administrador` > `instrutor` > `gestor` > `participante`.

## 5. Gestão de cursos e trilhas

Endpoints: `/api/v1/cursos` e `/api/v1/trilhas`

- CRUD completo de **trilhas** (`GET/POST/PATCH/DELETE /trilhas`)
- CRUD completo de **cursos** (`GET/POST/PATCH/DELETE /cursos`)
- **Módulos** (`/cursos/modulos`) e **unidades** (`/cursos/unidades`), com reordenação (`/reorder`)
- **Árvore de conteúdo**: `GET /cursos/{id}/arvore`
- **Inscrições**: `POST /cursos/inscricoes`, `GET /cursos/inscricoes/{usuario_id}`, `DELETE`
- **Turma do curso**: `GET /cursos/{id}/inscricoes` (retorna nome/email dos inscritos)
- **Inscritos na trilha**: `GET /trilhas/{id}/inscritos`
- **Progresso**: `GET /cursos/{id}/progresso/{usuario_id}`, `GET /trilhas/{id}/progresso`

## 6. Relatórios e dashboards

Endpoints: `/api/v1/dashboard` — restrito a gestor+admin+auditor.

| Operação | Endpoint |
|---|---|
| KPIs | `GET /dashboard/kpis` |
| Gráfico temporal | `GET /dashboard/graficos/temporal` |
| Resumo | `GET /dashboard/resumo` |
| Logs de acesso | `GET /dashboard/logs` |
| Relatório de desempenho | `GET /dashboard/relatorios/desempenho` |
| Relatório de presença | `GET /dashboard/relatorios/presenca` |
| Conteúdos acessados por usuário | `GET /dashboard/relatorios/conteudos-acessados?usuario_id=` |
| Métricas de engajamento | `GET /dashboard/metricas/{usuario_id}` |
| Coleta manual de métricas | `POST /dashboard/metricas/coletar` |

Filtros comuns: `curso_id`, `trilha_id`, `data_inicio`, `data_fim`, `formato=csv|pdf`.

## 7. Auditoria

Endpoints: `/api/v1/auditoria` — restrito a `administrador_geral` e `auditor`.

| Operação | Endpoint |
|---|---|
| Listar logs de auditoria | `GET /auditoria/logs` (filtros: tabela, usuário, ação, período) |
| Valores distintos para filtros | `GET /auditoria/opcoes` |
| Exportar CSV/PDF | `GET /auditoria/logs?formato=csv\|pdf` |

**Garantias:**

- `log_acesso`: grava operações de escrita (POST/PATCH/DELETE) com path e id.
- `log_auditoria`: snapshot completo (`dados_anteriores`/`dados_novos`) via `_serializar()`, com dados sensíveis removidos (LGPD).
- **Imutável**: a tabela `log_auditoria` tem trigger que bloqueia UPDATE/DELETE.

## 8. Certificados

Endpoints: `/api/v1/certificados`

| Operação | Endpoint |
|---|---|
| Emitir certificado | `POST /certificados` |
| Listar certificados de um usuário | `GET /certificados/usuario/{usuario_id}` |
| Ver certificado | `GET /certificados/{id}` |
| Modelos | `GET/POST /certificados/modelos` |
| Validar hash | `GET /certificados/validar/{hash}` |

- Emissão **automática** ao concluir o curso (via `progresso.py`).
- QR Code aponta para a rota pública de validação.
- Em S3, PDF/QR usam **URL presigned**.
- O CPF é **mascarado** na página pública (`***.456.789-***`).

## 9. Gamificação

Endpoints: `/api/v1/gamificacao`

- **Badges**: `GET/POST /gamificacao/badges`, `PATCH/DELETE /badges/{id}`, atribuir/conceder
- **Missões**: `GET/POST /gamificacao/missoes`, participantes, participar
- **Níveis**: `GET/POST /gamificacao/niveis`
- **XP**: `POST /gamificacao/xp`, `GET /gamificacao/xp/{usuario_id}/total`
- **Leaderboard**: `GET /gamificacao/leaderboard`, `GET /gamificacao/leaderboard/minha-posicao`
- **Streaks**: `GET /gamificacao/streaks/{usuario_id}`

## 10. Notificações

Endpoints: `/api/v1/notificacoes`

- Listar notificações do usuário: `GET /notificacoes`
- Marcar lida: `PATCH /notificacoes/{id}/lida`
- Marcar todas lidas: `POST /notificacoes/marcar-todas-lidas`

## 11. Boas práticas operacionais

1. **Nunca exclua** diretamente no banco — use os endpoints (a auditoria registra).
2. Antes de **deployar**, aplique as migrations: `alembic upgrade head` no banco alvo.
3. Confira o **health check**: `GET /health` deve retornar `database.ok`, `storage.ok` e `migrations` no head.
4. Para **exportar relatórios**, use `formato=csv` (planilha) ou `formato=pdf` (documento).
5. Roles do Keycloak são atribuídas pelo **IDESP** — não altere no backend.