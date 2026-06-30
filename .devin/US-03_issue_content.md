# US-03: Gestão de Perfis e Controle de Acesso (RBAC)

## Descrição

Como administrador, quero gerenciar os perfis dos usuários (administrador, instrutor, auditor, participante) para que cada pessoa tenha acesso apenas às funcionalidades pertinentes ao seu papel.

Hierarquia: ADM > Instrutor > Gestor > Aluno

Regras de negócio:
- **Gestor**: não preenche/salva avaliações, comentários, interações (apenas fiscaliza). Pode criar conta tipo aluno.
- **Instrutor**: pode fazer testes em sandbox de preencher avaliações, comentários etc.

## Tasks do Roadmap Afetadas

### Escopo direto da US-03:
- **Task 17.2** (movido de #55): Sistema de permissões granular baseado em hierarquia (RBAC)
- **Task 17.3** (movido de #56): Middleware para verificar permissões baseadas em hierarquia
- **Task 3**: Endpoint para listar usuários por perfil
- **Task 17.1**: Endpoint para gestor criar conta de participante (subordinado)
- **Task 30.1**: Modo sandbox para instrutor testar avaliações/comentários

### Tasks adicionadas ao roadmap (não existiam antes):
- 17.1, 30.1 (novas)
- 17.2, 17.3 (movidas de Extremamente Complexas para Médias-Altas)

## Análise Técnica

### O que já existe
- 6 perfis no banco: `administrador_geral`, `administrador`, `instrutor`, `auditor`, `gestor`, `participante`
- Model `Perfil` com coluna `permissoes` (JSONB, atualmente vazia `{}`)
- Tabela `usuario_perfil` com atribuição many-to-many
- `require_credenciamento` em `app/api/deps.py` (verifica apenas se usuário foi aprovado)
- Hierarquia de aprovação em `app/services/credenciamento.py`
- CRUD de usuários e perfis em `app/api/usuarios.py`

### O que precisa ser criado/modificado

#### 1. Sistema de Permissões (RBAC) — Task 17.2

**`app/services/rbac.py`** (novo)
- Constantes de permissão (ex: `AVALIACAO_CRIAR = "avaliacao:criar"`)
- Mapeamento perfil → permissões (dicionário)
- Função `get_user_permissions(user, db)` → list[str]
- Função `has_permission(user, permission, db)` → bool

**`app/permissions.py`** ou inline em `rbac.py`
- Definição central de todas as permissões do sistema

**`app/main.py`** — lifespan
- Seed das permissões nos perfis (popular `Perfil.permissoes`)

#### 2. Middleware de Permissões — Task 17.3

**`app/api/deps.py`**
- Nova dependência `require_permissao(permissao: str)` → Usuario
- Deve validar: usuário está autenticado → credenciado → tem a permissão

#### 3. Listar Usuários por Perfil — Task 3

**`app/api/usuarios.py`**
- Adicionar query param `?perfil_id=` ou `?perfil_nome=` no GET /usuarios
- Filtrar via join com `usuario_perfil` + `perfis`

#### 4. Gestor Criar Conta de Participante — Task 17.1

**`app/api/usuarios.py`** — novo endpoint
- `POST /usuarios/criar-subordinado`
- Apenas gestores podem acessar (require_permissao)
- Cria usuário com perfil participante, vincula ao gestor
- Requer migration para tabela `gestor_subordinado` (se não existir) ou usa campo `criado_por`

#### 5. Sandbox do Instrutor — Task 30.1

**`app/services/sandbox.py`** (novo)
- Lógica para criar sessão de teste
- Isolar dados de sandbox (flag `modo_teste` nas tabelas ou schema separado)

**Endpoints**
- `POST /sandbox/iniciar` — cria sessão sandbox
- `POST /sandbox/encerrar` — limpa dados de teste
- Avaliações/comentários criados em modo sandbox são descartados

### Permissões Definidas

```
avaliacao:criar
avaliacao:responder
avaliacao:editar
avaliacao:excluir
avaliacao:visualizar
comentario:criar
comentario:editar
comentario:excluir
comentario:visualizar
curso:criar
curso:editar
curso:excluir
curso:inscrever
curso:inscrever_outros
usuario:criar
usuario:editar
usuario:excluir
usuario:listar
relatorio:visualizar
dashboard:visualizar
credenciamento:aprovar
credenciamento:listar
sandbox:testar
```

### Mapeamento Perfil → Permissões

| Perfil | Permissões |
|--------|-----------|
| administrador_geral | todas |
| administrador | todas exceto auditoria |
| instrutor | avaliacao:* (criar,editar,excluir,responder,visualizar), comentario:* (criar,editar,excluir,visualizar), curso:criar,editar,excluir, sandbox:testar |
| auditor | relatorio:visualizar, dashboard:visualizar, avaliacao:visualizar, comentario:visualizar |
| gestor | usuario:criar, curso:inscrever_outros, relatorio:visualizar, dashboard:visualizar, comentario:visualizar, avaliacao:visualizar |
| participante | curso:inscrever, avaliacao:responder, avaliacao:visualizar, comentario:visualizar |

### Arquivos a Criar
- `app/services/rbac.py` — constantes, lógica de permissões
- `app/services/sandbox.py` — lógica de sandbox do instrutor

### Arquivos a Modificar
- `app/api/deps.py` — adicionar `require_permissao()`
- `app/api/usuarios.py` — listar por perfil, gestor criar subordinado
- `app/main.py` — seed de permissões no lifespan
- `app/api/__init__.py` — imports (se necessário)
- ROADMAP.md ✅ (já atualizado)
- AGENTS.md — documentar novos padrões RBAC

### Testes
- Validar que cada perfil tem as permissões corretas
- Validar que `require_permissao` bloqueia acesso sem a permissão
- Validar fluxo gestor criar subordinado
- Validar sandbox: dados de teste não persistem

## Critérios de Aceitação

- [ ] Perfis têm permissões granulares definidas e seeded
- [ ] `require_permissao()` funciona como dependency nos endpoints
- [ ] Endpoint GET /usuarios?perfil_nome=instrutor retorna filtrados
- [ ] Gestor pode criar conta de participante via endpoint
- [ ] Instrutor pode iniciar/encerrar sandbox e testar avaliações/comentários
- [ ] Gestor NÃO consegue criar/editar avaliações ou comentários
- [ ] Participante NÃO consegue criar cursos ou avaliar
- [ ] Nada quebrado — imports funcionando, metadata consistente
