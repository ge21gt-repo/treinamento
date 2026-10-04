# LMS IDE-SP — Backend API

Plataforma de Capacitação e Treinamento do Projeto IDE-SP.

## Stack

- **Python 3.12** + **FastAPI**
- **PostgreSQL 15+** com schema `lms`
- **SQLAlchemy 2.0** (async) + **Alembic** (async migrations)
- **JWT** (python-jose) + **bcrypt** (passlib)
- **S3** (aioboto3) para armazenamento de arquivos
- **Microsoft Graph API** (httpx) para integração Teams
- Deploy via **fly.io** (Docker, porta 8080)

## Setup Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edite DATABASE_URL e SECRET_KEY
alembic upgrade head
psql $DATABASE_URL -f scripts/init_db.sql   # schema lms, extensões, seeds, índices
uvicorn app.main:app --reload
```

> O app também auto-cria tabelas e seeds (perfis, níveis, permissões RBAC) no startup via FastAPI lifespan. O passo `alembic upgrade head` + `init_db.sql` é opcional em dev, mas obrigatório em staging/prod.

## Build Jenkins / GKE

O job `applications/treinamento-idesp-api`, definido em
`IDESP-CICD/treinamento-idesp-api/Jenkinsfile`, faz checkout, constrói e publica
a imagem e aplica o manifesto GKE. A instalação de `requirements.txt` pertence
ao próprio Dockerfile: não há script de preparo, venv externo ou artefato
pré-compilado no workspace.

Antes do build da imagem, `Prepare tools` instala requirements diretamente no
Python do agente, configura Buildx e instala/inicia PostgreSQL 16 temporário
no mesmo container. Não altera a imagem base nem adiciona container ao pod.
O servidor roda como usuário `postgres`, escuta somente em loopback e é
encerrado no cleanup; pacotes e dados são descartados com o pod.
`Tests` chama pytest na raiz usando o `pytest.ini`, sem venv, com storage local.
Não usa banco ou credenciais de produção. A preparação cria schema/metadata Alembic para
os testes de health; as tabelas são criadas pelas fixtures dos testes.
Não é uma validação da cadeia de migrations.
O XML `.build/test-results/pytest.xml` é publicado pelo plugin JUnit do Jenkins
mesmo quando testes falham, com resultados, duração e histórico no job.
Falha de teste ou relatório ausente bloqueia publicação/deploy.
Os relatórios `.build` são temporários e excluídos pelo `.dockerignore`.

```mermaid
flowchart LR
    R[treinamento<br/>requirements.txt e app] -->|checkout SOURCE_BRANCH| J[Jenkins<br/>python-3.12]
    J -->|docker buildx build| D[Dockerfile<br/>pip install + runtime]
    D -->|BuildKit rootless e push| G[(GAR idesp-prod-apps)]
    J -->|IMAGE_URI e kubeconfig-gke-prd| K[GKE<br/>k8s/treinamento-idesp-api.yaml]
    G -->|pull imagem| K
```

O [Dockerfile](Dockerfile) usa `python:3.12-slim-trixie` num único estágio,
instala os requirements com `pip install --no-cache-dir` e executa `pip check`.
Depois copia o source completo com `COPY . /app/`, incluindo `scripts/`,
documentação, Alembic e demais arquivos, respeitando o `.dockerignore`.
As exclusões ficam centralizadas nele: secrets `.env*` (exceto `.env.example`),
Git, ambientes virtuais, caches, testes, workflows, artefatos `.build`, uploads
locais, screenshots e configuração `.devin`. Não há lista de arquivos
permitidos no Dockerfile; novas exclusões funcionais devem ser avaliadas com
os desenvolvedores. Executa como UID/GID `10001`, escuta na porta 8080 e mantém
`/app/uploads/_chunks` gravável: uploads em chunks usam disco temporário mesmo
com S3. Esse diretório não é persistente nem compartilhado entre réplicas;
afinidade/persistência de uploads retomáveis é uma decisão de infraestrutura
separada, não resolvida por esta imagem.

O argumento `BASE_IMAGE` aceita outra base Python 3.12 compatível; o padrão é
`python:3.12-slim-trixie`. Não há runtime Python própria no GAR.
Pip permanece disponível, sem cache de instalação; não há compilador na
imagem final. As dependências atuais têm wheels compatíveis com essa base.
Se uma dependência futura precisar de compilação, ferramentas devem ficar
fora da imagem final; reavaliar o empacotamento específico dessa dependência.
O empacotamento usa root para instalar dependências e ajustar os diretórios;
o processo final sempre executa como `10001:10001`, inclusive na base oficial.

Parâmetros do job: `SOURCE_BRANCH` (padrão `development`) e `AMBIENTE`
(`gke-prd`). Faz checkout com `github-repositories`, publica
`idesp-prod-apps/treinamento-idesp-api:<data>-<sha>` e aplica o manifesto com
`kubeconfig-gke-prd`. Imagem, container, Deployment, Service, Ingress e HPA
usam `treinamento-idesp-api`; o arquivo é `k8s/treinamento-idesp-api.yaml`.
O rollout usa namespace/nome lidos do manifesto e tenta
rollback em caso de falha.

Endereço público no GKE: `https://igc.idesp.sp.gov.br/treinamento-api`
(interface em `/treinamento`). O Ingress é minion do master `edge/igc-host` e
remove o prefixo, então a app continua servindo `/api/v1` e `/health`;
`ROOT_PATH=/treinamento-api` só ajusta OpenAPI, `/docs` e `tokenUrl`.

Renomear recursos não migra nem remove objetos Kubernetes existentes.
Se `treinamento-backend` já estiver no cluster, planejar a troca e retirada
controlada dos recursos antigos, evitando dois Ingresses para o mesmo host
e workloads duplicados. Secrets externos mantêm seus nomes atuais.

O job não executa testes nem migrações em banco de produção. Antes do deploy, a equipe
deve reconciliar/aplicar Alembic no banco de destino e conferir
`/health → checks.migrations`; `create_all()` não substitui migrações.

### Build local com as mesmas bases

Requer Docker e acesso às imagens oficiais e ao índice de pacotes:

```bash
docker build -t treinamento-idesp-api:local .
```

Para substituir explicitamente a base padrão:

```bash
docker build --build-arg BASE_IMAGE=python:3.12-slim-trixie \
  -t treinamento-idesp-api:local .
```

Ambos os comandos partem apenas do source; o Docker instala os requirements.
Não há leitura de uma base privada do GAR nem multistage.

### Compatibilidade com deploy AWS / Fly

O [deploy automático AWS](.github/workflows/deploy.yml) de
`development`/`homologacao` envia o source no tarball e executa `docker build`,
como antes, usando a base oficial padrão. O Dockerfile instala as dependências durante
esse build. O processo da aplicação passa a executar como UID/GID 10001 também
nesse fluxo; conferir permissões de qualquer volume de uploads existente.

O exemplo Fly usa o mesmo Dockerfile e sua base padrão, sem preparo externo.
O nome legado `treinamento-backend` no workflow AWS é preservado porque o
Docker Compose da EC2 é externo a este repositório. A padronização acima
abrange Jenkins/GAR/GKE; não altera esse contrato do deploy AWS.

Esta branch parte de `feature/k8s-manifesto` e retorna para ela por PR.
Depois de integrar o manifesto e estas alterações em `development` e a pipeline
em `IDESP-CICD/master`, executar **Sincronizar pipelines** e iniciar o job real
manualmente. A execução inicial do sincronizador é cancelada. Antes da integração,
é possível testar `SOURCE_BRANCH` com a branch do PR da aplicação.
O merge em `development` ainda dispara deploy AWS; exige as verificações de
migração e aprovação operacional habituais.

O [CI](.github/workflows/ci.yml) permanece no formato original: lint, imports,
verificações de segurança e pytest para pushes/PRs de `main`. Não constrói
imagens Docker. O build/deploy pertence ao workflow de deploy e ao Jenkins.

### Depuração do empacotamento

```bash
docker run --rm treinamento-idesp-api:local python -m uvicorn --version
docker run --rm treinamento-idesp-api:local python -m alembic heads
kubectl -n apps rollout status deployment/treinamento-idesp-api --timeout=5m
kubectl -n apps logs deployment/treinamento-idesp-api --tail=100
```

| Sintoma | Causa provável |
|---|---|
| `pip install` falha no build | Versões incompatíveis, acesso ao índice de pacotes ou wheel ausente; conferir log do Docker build |
| Agente em `ImagePullBackOff` | Tag `jenkins-agent-python:python3.12` ausente ou agente JCasC não aplicado |
| Import de extensão nativa falha | Pacote ou biblioteca do sistema incompatível com Python / distribuição / arquitetura |
| Upload retorna erro de permissão | Volume montado em `/app/uploads` não permite escrita pelo UID 10001 |
| Rollout falha | Conferir eventos, Secrets, probes e logs; o rollback não desfaz migrações |
| Build tenta ler a runtime GAR antiga | Dockerfile desatualizado ou override antigo de `BASE_IMAGE` |

## Testes

O projeto possui **49 testes de integração** que batem contra **PostgreSQL real** e **S3 real** (ou local storage). Nenhum mock — cada teste cria/consulta/limpa dados de verdade via API HTTP.

### O que é testado

| Arquivo | Testes | Cobertura |
|---------|--------|-----------|
| `tests/test_auth.py` | 8 | Registro, login, LGPD obrigatório, email duplicado, JWT, solicitação pendente |
| `tests/test_rbac.py` | 9 | Autenticação (sem token, token inválido), permissões de curso/inscrição/conteúdo por perfil |
| `tests/test_us05.py` | 10 | Aulas síncronas (CRUD + próximas), chat do curso (enviar + listar), reordenação de módulos e unidades, árvore aninhada |
| `tests/test_us06.py` | 22 | Upload de arquivos (PDF, vídeo, MIME inválido), CRUD de conteúdo, materiais complementares, entregas de atividades (upload, listar, corrigir), SCORM (upload, launch, tracking, relatório) |
| `tests/test_bug_fix_18.py` | — | Regressão do bug `AmbiguousForeignKeysError` no cadastro de usuário |

### Como funciona

- Cada suite cria seus próprios dados via **HTTP requests** (`httpx.AsyncClient`) contra a aplicação real
- O banco é limpo entre fixtures (`TRUNCATE CASCADE`), mantendo perfis e permissões
- Uploads vão para S3 ou disco local conforme `STORAGE_BACKEND` do `.env`
- Dependências como `get_db` e `get_current_user` são sobrescritas via `app.dependency_overrides`

### Executar

```bash
pytest                                   # todos os testes
pytest tests/test_us06.py -v            # apenas uploads/SCORM
pytest tests/test_auth.py -x            # para no primeiro erro
```

> Requer PostgreSQL rodando com as credenciais do `.env` (`DATABASE_URL`). O schema `lms` e as tabelas são criados automaticamente.

---

**Arquivo `.env`:**

| Variável | Default | Descrição |
|----------|---------|-----------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/lms_idesp` | Conexão com PostgreSQL (auto-converte para asyncpg) |
| `SECRET_KEY` | `change-me-in-production` | Chave para assinar JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Expiração do token JWT |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Origens CORS permitidas |
| `STORAGE_BACKEND` | `local` | `local` (disco) ou `s3` (AWS S3) |
| `S3_ENDPOINT` | `""` | Endpoint S3 personalizado (vazio = padrão AWS) |
| `S3_ACCESS_KEY` | `""` | AWS Access Key ID |
| `S3_SECRET_KEY` | `""` | AWS Secret Access Key |
| `S3_BUCKET` | `lms-conteudos` | Nome do bucket S3 |
| `S3_REGION` | `us-east-1` | Região AWS |
| `MAX_UPLOAD_SIZE` | `524288000` | Tamanho máximo de upload (500MB) |
| `TEAMS_TENANT_ID` | `""` | Azure AD Tenant ID (Teams) |
| `TEAMS_CLIENT_ID` | `""` | Azure AD App Registration Client ID |
| `TEAMS_CLIENT_SECRET` | `""` | Azure AD Client Secret |
| `TEAMS_ORGANIZER_EMAIL` | `""` | Email da conta de serviço com licença Teams |
| `SMTP_HOST` | `localhost` | Servidor SMTP (recuperação de senha) |
| `SMTP_PORT` | `587` | Porta SMTP |
| `SMTP_USER` | `""` | Usuário SMTP |
| `SMTP_PASSWORD` | `""` | Senha SMTP |
| `SMTP_FROM` | `noreply@lms-idesp.com` | Remetente de emails |
| `SMTP_TLS` | `true` | TLS no SMTP |
| `RESET_TOKEN_EXPIRE_MINUTES` | `60` | Expiração do token de redefinição de senha |
| `BASE_URL` | `http://localhost:8000/api/v1` | URL pública da API para links nos emails e no QR Code do certificado |
| `ROOT_PATH` | `""` | Prefixo público quando um proxy o remove antes da app (GKE: `/treinamento-api`) |

---

## Endpoints

**Base:** `/api/v1` · **Docs:** `/docs` (Swagger) · `/redoc` (ReDoc)

### Autenticação e Credenciamento

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| POST | `/auth/registro` | `UsuarioCreate` | `UsuarioRead` (201) — cria participante ativo |
| POST | `/auth/registro-com-perfil` | `UsuarioRegistro` | `{"message", "solicitacao_id"}` (201) — solicitação pendente |
| POST | `/auth/login` | `LoginRequest` | `{"access_token": str, "token_type": "bearer"}` |
| POST | `/auth/logout` | — | `{"message"}` |
| POST | `/auth/esqueci-senha` | `EsqueciSenhaRequest` | `{"message"}` — envia email |
| POST | `/auth/redefinir-senha` | `RedefinirSenhaRequest` | `{"message"}` |
| GET | `/credenciamento/solicitacoes/pendentes` | — | `list[SolicitacaoCredenciamentoRead]` |
| POST | `/credenciamento/solicitacoes/{id}/aprovar` | `AprovacaoSolicitacaoRequest` | `{"message", "usuario"}` |
| POST | `/credenciamento/solicitacoes/{id}/rejeitar` | `AprovacaoSolicitacaoRequest` | `{"message"}` |

### Usuários e Perfis

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/usuarios` | `?skip=0&limit=50&perfil_nome=` | `list[UsuarioRead]` |
| GET | `/usuarios/me` | — | `UsuarioRead` |
| GET | `/usuarios/{id}` | — | `UsuarioRead` |
| PATCH | `/usuarios/{id}` | `UsuarioUpdate` | `UsuarioRead` |
| DELETE | `/usuarios/{id}` | — | 204 |
| POST | `/usuarios/criar-subordinado` | `CriarSubordinadoRequest` | `UsuarioRead` (201) |
| GET | `/usuarios/perfis/todos` | — | `list[PerfilRead]` |
| POST | `/usuarios/perfis` | `PerfilCreate` | `PerfilRead` (201) |
| PATCH | `/usuarios/perfis/{id}` | `PerfilUpdate` | `PerfilRead` |
| DELETE | `/usuarios/perfis/{id}` | — | 204 |
| POST | `/usuarios/perfis/atribuir` | `UsuarioPerfilCreate` | `{"detail"}` (201) |

### Trilhas de Aprendizagem

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/trilhas` | `?skip=0&limit=50&nivel=` | `list[TrilhaRead]` |
| POST | `/trilhas` | `TrilhaCreate` | `TrilhaRead` (201) |
| GET | `/trilhas/minhas-trilhas` | — | `list[TrilhaProgressoRead]` |
| GET | `/trilhas/{id}` | — | `TrilhaRead` |
| PATCH | `/trilhas/{id}` | `TrilhaUpdate` | `TrilhaRead` |
| DELETE | `/trilhas/{id}` | — | 204 |
| POST | `/trilhas/{id}/inscrever` | — | `InscricaoTrilhaRead` (201) |
| GET | `/trilhas/{id}/progresso` | — | `TrilhaProgressoRead` |

### Cursos, Módulos e Unidades

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/cursos` | `?skip=0&limit=50&trilha_id=` | `list[CursoRead]` |
| POST | `/cursos` | `CursoCreate` | `CursoRead` (201) |
| GET | `/cursos/{id}` | — | `CursoRead` |
| PATCH | `/cursos/{id}` | `CursoUpdate` | `CursoRead` |
| DELETE | `/cursos/{id}` | — | 204 |
| GET | `/cursos/{id}/arvore` | — | `CursoArvoreRead` (árvore aninhada) |
| GET | `/cursos/{id}/modulos` | — | `list[ModuloRead]` |
| POST | `/cursos/modulos` | `ModuloCreate` | `ModuloRead` (201) |
| PATCH | `/cursos/modulos/{id}` | `ModuloUpdate` | `ModuloRead` |
| DELETE | `/cursos/modulos/{id}` | — | 204 |
| PATCH | `/cursos/modulos/reorder` | `list[ReorderItem]` | 204 |
| GET | `/cursos/modulos/{modulo_id}/unidades` | — | `list[UnidadeRead]` |
| POST | `/cursos/unidades` | `UnidadeCreate` | `UnidadeRead` (201) |
| PATCH | `/cursos/unidades/{id}` | `UnidadeUpdate` | `UnidadeRead` |
| DELETE | `/cursos/unidades/{id}` | — | 204 |
| PATCH | `/cursos/unidades/reorder` | `list[ReorderItem]` | 204 |
| GET | `/cursos/{id}/consumo` | — | `dict` — curso completo com módulos, unidades, conteúdos, progresso, entregas |
| POST | `/cursos/inscricoes` | `InscricaoCreate` | `InscricaoRead` (201) — valida pré-requisito |
| GET | `/cursos/inscricoes/{usuario_id}` | — | `list[InscricaoRead]` |
| POST | `/cursos/progresso` | `ProgressoUnidadeCreate` | `ProgressoUnidadeRead` (201) |
| PATCH | `/cursos/progresso/{id}` | `ProgressoUnidadeUpdate` | `ProgressoUnidadeRead` |

#### Aulas Síncronas

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/cursos/{curso_id}/aulas` | — | `list[AulaSincronaRead]` |
| POST | `/cursos/{curso_id}/aulas` | `AulaSincronaCreate` (com `criar_reuniao_teams`) | `AulaSincronaRead` (201) — se Teams configurado, cria reunião automática |
| GET | `/cursos/aulas/proximas` | — | `list[AulaSincronaRead]` |
| PATCH | `/cursos/aulas/{id}` | `AulaSincronaUpdate` | `AulaSincronaRead` |
| DELETE | `/cursos/aulas/{id}` | — | 204 |

#### Chat do Curso (SSE)

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/cursos/{curso_id}/chat` | `?page=1&limit=50` | `list[{id, usuario_id, texto, criado_em}]` |
| POST | `/cursos/{curso_id}/chat` | `{"texto": str}` | `{id, usuario_id, texto, criado_em}` (201) |
| GET | `/cursos/{curso_id}/chat/stream` | — | SSE — mensagens em tempo real |

### Conteúdos Multimídia (US-06)

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/conteudos` | `?unidade_id=&skip=0&limit=50` | `list[ConteudoRead]` |
| POST | `/conteudos` | `ConteudoCreate` | `ConteudoRead` (201) |
| **POST** | **`/conteudos/upload`** | **`unidade_id`, `tipo_midia`, `titulo` + arquivo (multipart)** | **`ConteudoRead` (201) — salva no S3 ou local** |
| GET | `/conteudos/{id}` | — | `ConteudoRead` |
| GET | `/conteudos/{id}/player` | — | `ConteudoRead` (URL para player) |
| PATCH | `/conteudos/{id}` | `ConteudoUpdate` | `ConteudoRead` |
| DELETE | `/conteudos/{id}` | — | 204 — deleta arquivo do S3 |

#### Materiais Complementares

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/conteudos/materiais/{curso_id}` | — | `list[MaterialComplementarRead]` |
| POST | `/conteudos/materiais` | `MaterialComplementarCreate` | `MaterialComplementarRead` (201) |
| **POST** | **`/conteudos/materiais/upload`** | **`curso_id`, `titulo`, `tipo` + arquivo (multipart)** | **`MaterialComplementarRead` (201)** |
| PATCH | `/conteudos/materiais/{id}` | `MaterialComplementarUpdate` | `MaterialComplementarRead` |
| DELETE | `/conteudos/materiais/{id}` | — | 204 |

### Entregas de Atividades

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| **POST** | **`/entregas/upload`** | **`unidade_id`, `titulo`, `descricao` + arquivo (multipart)** | **`EntregaAtividadeRead` (201) — `status="pendente"`** |
| GET | `/entregas/unidade/{unidade_id}` | — | `list[EntregaAtividadeRead]` |
| GET | `/entregas/minhas` | — | `list[EntregaAtividadeRead]` |
| GET | `/entregas/usuario/{usuario_id}` | — | `list[EntregaAtividadeRead]` |
| GET | `/entregas/{id}` | — | `EntregaAtividadeRead` |
| **PATCH** | **`/entregas/{id}/corrigir`** | **`EntregaAtividadeCorrigir` (`nota`, `feedback`)** | **`EntregaAtividadeRead` — `status="corrigido"`** |

### SCORM

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| **POST** | **`/scorm/upload`** | **`curso_id`, `titulo` + ZIP (multipart)** | **`PacoteScormRead` (201) — parse do imsmanifest.xml** |
| GET | `/scorm/{pacote_id}/launch` | `?sco_id=` | `ScormLaunchResponse` (`url`, `token`, `sco_id`) |
| POST | `/scorm/{pacote_id}/tracking` | `TrackingScormCreate` | `TrackingScormRead` — upsert por usuário + pacote + sco_id |
| GET | `/scorm/{pacote_id}/tracking` | — | `list[TrackingScormRead]` |
| GET | `/scorm/cursos/{curso_id}/relatorio` | — | `list[ScormRelatorioItem]` |

### Sandbox do Instrutor

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| POST | `/sandbox/iniciar` | `SandboxIniciarRequest` | `SandboxSessaoRead` (201) |
| POST | `/sandbox/{id}/encerrar` | — | `{"message", "discarded_items"}` |
| GET | `/sandbox/ativo` | — | `SandboxSessaoRead \| null` |
| GET | `/sandbox/sessoes` | — | `list[SandboxSessaoRead]` |

### Avaliações

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/avaliacoes` | `?unidade_id=&skip=0&limit=50` | `list[AvaliacaoRead]` |
| POST | `/avaliacoes` | `AvaliacaoCreate` | `AvaliacaoRead` (201) |
| GET | `/avaliacoes/{id}` | — | `AvaliacaoRead` |
| PATCH | `/avaliacoes/{id}` | `AvaliacaoUpdate` | `AvaliacaoRead` |
| DELETE | `/avaliacoes/{id}` | — | 204 |
| GET | `/avaliacoes/{id}/questoes` | — | `list[QuestaoRead]` |
| POST | `/avaliacoes/questoes` | `QuestaoCreate` | `QuestaoRead` (201) |
| PATCH | `/avaliacoes/questoes/{id}` | `QuestaoUpdate` | `QuestaoRead` |
| GET | `/avaliacoes/questoes/{id}/alternativas` | — | `list[AlternativaRead]` |
| POST | `/avaliacoes/alternativas` | `AlternativaCreate` | `AlternativaRead` (201) |
| POST | `/avaliacoes/respostas` | `RespostaParticipanteCreate` | `RespostaParticipanteRead` (201) |
| POST | `/avaliacoes/resultados` | `ResultadoAvaliacaoCreate` | `ResultadoAvaliacaoRead` (201) |
| GET | `/avaliacoes/resultados/{usuario_id}` | — | `list[ResultadoAvaliacaoRead]` |

### Certificados

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/certificados/modelos` | — | `list[ModeloCertificadoRead]` |
| POST | `/certificados/modelos` | `ModeloCertificadoCreate` | `ModeloCertificadoRead` (201) |
| POST | `/certificados` | `CertificadoCreate` | `CertificadoRead` (201) |
| GET | `/certificados/{id}` | — | `CertificadoRead` |
| GET | `/certificados/validar/{hash}` | — | `CertificadoRead` (público) |
| GET | `/certificados/usuario/{usuario_id}` | — | `list[CertificadoRead]` |

### Gamificação

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/gamificacao/niveis` | — | `list[NivelRead]` |
| POST | `/gamificacao/niveis` | `NivelCreate` | `NivelRead` (201) |
| POST | `/gamificacao/xp` | `PontosXPCreate` | `PontosXPRead` (201) |
| GET | `/gamificacao/xp/{usuario_id}` | — | `list[PontosXPRead]` |
| GET | `/gamificacao/xp/{usuario_id}/total` | — | `{usuario_id, xp_total, nivel}` |
| GET | `/gamificacao/leaderboard` | `?limit=10` | `list[LeaderboardEntry]` |
| GET | `/gamificacao/badges` | — | `list[BadgeRead]` |
| POST | `/gamificacao/badges` | `BadgeCreate` | `BadgeRead` (201) |
| POST | `/gamificacao/badges/atribuir` | `UsuarioBadgeCreate` | `UsuarioBadgeRead` (201) |
| GET | `/gamificacao/badges/{usuario_id}` | — | `list[UsuarioBadgeRead]` |
| GET | `/gamificacao/missoes` | — | `list[MissaoRead]` |
| POST | `/gamificacao/missoes` | `MissaoCreate` | `MissaoRead` (201) |
| PATCH | `/gamificacao/missoes/{id}` | `MissaoUpdate` | `MissaoRead` |
| POST | `/gamificacao/missoes/participar` | `UsuarioMissaoCreate` | `UsuarioMissaoRead` (201) |
| PATCH | `/gamificacao/missoes/usuario/{id}` | `UsuarioMissaoUpdate` | `UsuarioMissaoRead` |
| GET | `/gamificacao/streaks/{usuario_id}` | — | `StreakRead` |

### Sessões ao Vivo

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/sessoes` | `?curso_id=&skip=0&limit=50` | `list[SessaoAoVivoRead]` |
| POST | `/sessoes` | `SessaoAoVivoCreate` | `SessaoAoVivoRead` (201) |
| GET | `/sessoes/{id}` | — | `SessaoAoVivoRead` |
| PATCH | `/sessoes/{id}` | `SessaoAoVivoUpdate` | `SessaoAoVivoRead` |
| DELETE | `/sessoes/{id}` | — | 204 |
| POST | `/sessoes/presenca` | `PresencaCreate` | `PresencaRead` (201) |
| GET | `/sessoes/presenca/{sessao_id}` | — | `list[PresencaRead]` |
| PATCH | `/sessoes/presenca/{id}` | `PresencaUpdate` | `PresencaRead` |

### Comunicação (Chat Geral e Fórum)

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| POST | `/comunicacao/chat` | `MensagemChatCreate` | `MensagemChatRead` (201) |
| GET | `/comunicacao/chat/{sessao_id}` | `?skip=0&limit=100` | `list[MensagemChatRead]` |
| GET | `/comunicacao/forum/{curso_id}` | `?skip=0&limit=50` | `list[ForumTopicoRead]` |
| POST | `/comunicacao/forum` | `ForumTopicoCreate` | `ForumTopicoRead` (201) |
| GET | `/comunicacao/forum/topico/{id}` | — | `ForumTopicoRead` |
| PATCH | `/comunicacao/forum/topico/{id}` | `ForumTopicoUpdate` | `ForumTopicoRead` |
| DELETE | `/comunicacao/forum/topico/{id}` | — | 204 |
| GET | `/comunicacao/forum/topico/{id}/respostas` | — | `list[ForumRespostaRead]` |
| POST | `/comunicacao/forum/respostas` | `ForumRespostaCreate` | `ForumRespostaRead` (201) |

### Dashboard e Analytics

| Método | Rota | Input | Output |
|--------|------|-------|--------|
| GET | `/dashboard/resumo` | — | `{total_usuarios, total_cursos, total_trilhas, total_inscricoes, total_certificados, total_sessoes_ao_vivo}` |
| GET | `/dashboard/metricas/{usuario_id}` | `?limit=30` | `list[MetricaEngajamentoRead]` |
| GET | `/dashboard/logs` | `?usuario_id=&skip=0&limit=50` | `list[LogAcessoRead]` |
| GET | `/dashboard/cursos/{curso_id}/stats` | — | `{total_inscritos, total_concluidos, nota_media, taxa_conclusao}` |

---

## Storage (S3)

Arquivos enviados por upload vão para o **bucket S3** `lms-conteudos`. A escolha entre S3 e disco local é feita via `STORAGE_BACKEND` no `.env`.

**Pastas no bucket:**
- `videos/` — MP4, WebM, AVI
- `pdfs/` — PDF
- `audio/` — MP3, WAV, OGG
- `images/` — JPEG, PNG, WebP
- `scorm/` — ZIP de pacotes SCORM
- `exercicios/` — entregas de alunos
- `complementares/` — materiais complementares

**Validação:** MIME type e tamanho máximo (500MB) são verificados antes do upload. `MAX_UPLOAD_SIZE` no `.env`.

### Presigned URLs (url_acesso)

Os uploads são salvos como objetos **privados** no S3. Para acessá-los, o backend gera **URLs assinadas** temporárias (`X-Amz-Signature`):

| Campo | Descrição |
|-------|-----------|
| `url_arquivo` | URL direta do S3 (retorna 403 se o objeto é privado) |
| `url_acesso` | URL assinada válida por **1 hora** (use esta para exibir/baixar) |

**Schemas que expõem `url_acesso`:** `ConteudoRead`, `MaterialComplementarRead`, `EntregaAtividadeRead`, `PacoteScormRead`, `ScormLaunchResponse`, `UnidadeRead`, `CursoArvoreItem`.

Em storage local (`STORAGE_BACKEND=local`), `url_acesso` retorna o mesmo valor de `url_arquivo`.

---

## Teams / Microsoft Graph

Integração opcional com Microsoft Teams para aulas síncronas. Existem dois fluxos:

### Fluxo A — Automático (Teams via API)

Usado quando o ambiente tem as permissões do Azure configuradas.

1. **Criar aula com reunião Teams**
   `POST /cursos/{id}/aulas` com `"criar_reuniao_teams": true`
   - Backend chama `POST /users/{organizador}/onlineMeetings` no Graph API
   - Retorna `joinWebUrl` + `meetingId` → salvos nos campos `link_externo` e `teams_meeting_id` da `AulaSincrona`

2. **Professor e alunos participam**
   - Entram pelo link gerado: `https://teams.microsoft.com/l/meetup-join/19%...`
   - Professor clica em **"Gravar"** durante a aula

3. **Processar gravação (pós-aula)**
   `POST /cursos/aulas/{id}/processar-gravacao`
   - Backend chama `GET /onlineMeetings/{id}/recordings` no Graph API
   - Baixa o arquivo MP4 (vídeo da gravação)
   - Faz upload para o S3 via `storage.upload_bytes()`
   - Cria um registro `Conteudo` com `tipo_midia="video"` e vincula em `gravacao_conteudo_id` na aula

4. **Aluno assiste**
   - Ao acessar a aula, o frontend usa `url_acesso` do conteúdo vinculado
   - O player reproduz o MP4 direto do S3 via URL assinada (válida por 1h)

**Permissões necessárias no Azure AD:**
- `OnlineMeetings.ReadWrite.All` — criar reuniões
- `OnlineMeetingRecording.Read.All` — baixar gravações
- `OnlineMeetingAttendanceReport.Read.All` — lista de presença

### Fluxo B — Manual (link externo + upload)

Usado quando o Teams não está integrado ou o professor prefere outro provedor.

1. **Criar aula com link manual**
   `POST /cursos/{id}/aulas` com `"link_externo": "https://meet.google.com/..."` (ou Zoom, Teams manual, etc.)
   - Nenhuma chamada ao Graph API é feita
   - O link é salvo diretamente na `AulaSincrona`

2. **Aula acontece normalmente** no provedor externo

3. **Upload manual da gravação**
   - Professor baixa o MP4 do provedor
   - Faz upload via `POST /conteudos/upload` → recebe um `conteudo_id`
   - Vincula à aula: `PATCH /cursos/aulas/{id}` com `{"gravacao_conteudo_id": <id>}`

4. **Aluno assiste** — mesmo fluxo, o frontend exibe o player com `url_acesso`

### Resumo dos dois fluxos

| | Automático (Teams API) | Manual (link externo) |
|---|---|---|
| Criação da reunião | API do Teams cria automático | Professor cria por fora e passa o link |
| Link na aula | `joinWebUrl` gerado pela API | `link_externo` informado manualmente |
| Gravação | `processar-gravacao` baixa do Teams | Professor faz upload do MP4 |
| Complexidade | Zero esforço manual | Professor baixa + faz upload |
| Requer Azure | Sim (permissões configuradas) | Não

---

## SCORM

Suporte a pacotes SCORM 1.2 e 2004.

**Fluxo:**
1. `POST /scorm/upload` — recebe ZIP, parseia `imsmanifest.xml`, extrai organizations/resources/items
2. `GET /scorm/{id}/launch` — gera JWT token + URL para o player
3. `POST /scorm/{id}/tracking` — upsert de dados CMI por (usuário, pacote, sco_id)
4. `GET /scorm/cursos/{id}/relatorio` — relatório agregado para o instrutor

---

## Controle de Acesso (RBAC)

**38 permissões** distribuídas em 6 perfis:

| Permissão | admin_geral | admin | instrutor | auditor | gestor | participante |
|-----------|:-----------:|:-----:|:---------:|:-------:|:------:|:------------:|
| `avaliacao:*` (CRUD) | ✅ | ✅ | ✅ | | | |
| `avaliacao:responder` | ✅ | ✅ | | | | ✅ |
| `avaliacao:visualizar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `comentario:*` (CRUD) | ✅ | ✅ | ✅ | | | |
| `comentario:visualizar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `curso:*` (CRUD) | ✅ | ✅ | ✅ | | | |
| `curso:inscrever` | ✅ | ✅ | ✅ | | | ✅ |
| `curso:inscrever_outros` | ✅ | ✅ | | | ✅ | |
| `usuario:*` (CRUD) | ✅ | ✅ | | | | |
| `usuario:criar` | ✅ | ✅ | | | ✅ | |
| `relatorio:visualizar` | ✅ | ✅ | | ✅ | ✅ | |
| `dashboard:visualizar` | ✅ | ✅ | | ✅ | ✅ | |
| `credenciamento:*` | ✅ | ✅ | | | | |
| `sandbox:testar` | ✅ | ✅ | ✅ | | | |
| `trilha:*` (CRUD) | ✅ | ✅ | ✅ | | | |
| `trilha:inscrever` | ✅ | ✅ | ✅ | | ✅ | ✅ |
| `trilha:ver_progresso` | ✅ | ✅ | ✅ | | ✅ | ✅ |
| `conteudo:*` (CRUD) | ✅ | ✅ | ✅ | | | |
| `conteudo:visualizar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `material:gerenciar` | ✅ | ✅ | ✅ | | | |
| `entrega:criar` | | | | | | ✅ |
| `entrega:visualizar` | ✅ | ✅ | ✅ | | ✅ | ✅ |
| `entrega:corrigir` | ✅ | ✅ | ✅ | | | |
| `scorm:gerenciar` | ✅ | ✅ | ✅ | | | |
| `scorm:visualizar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Uso em endpoints:
```python
from app.services.rbac import Permissoes
from app.api.deps import require_permissao

@router.post("/avaliacoes")
async def criar_avaliacao(
    ...,
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_CRIAR)),
):
```

---

## Fluxo de Credenciamento

1. Usuário registra com perfil → solicitação **pendente** (usuário inativo)
2. Superior hierárquico lista pendentes → aprova/rejeita
3. Usuário aprovado vira **ativo** com perfil atribuído
4. Middleware `require_credenciamento` bloqueia não aprovados

Hierarquia: `admin_geral > admin > instrutor > gestor > participante`

---

## Arquitetura

```
app/
├── api/           # FastAPI route modules (1 por domínio, 15 módulos)
├── models/        # SQLAlchemy models (schema lms, ~44 tabelas)
├── schemas/       # Pydantic v2 schemas (from_attributes)
├── services/      # Lógica de negócio (RBAC, Storage, Teams)
├── config.py      # Settings via .env
├── database.py    # Async engine + session factory
└── main.py        # Entrypoint + lifespan (auto-migrate + seeds)
```

### Modelo de Dados

44 tabelas no schema `lms`, organizadas em 15 domínios.
Veja `scripts/init_db.sql` para DDL completo, extensões (`pgcrypto`, `citext`), seeds e índices.

---

## Perfis Públicos

- `/health` → `{"status": "ok"}`
- `/docs` → Swagger UI
- `/redoc` → ReDoc

---

## Deploy (fly.io)

```bash
fly launch
fly postgres create --name lms-idesp-db --region gru
fly postgres attach lms-idesp-db
fly secrets set SECRET_KEY="sua-chave-secreta"
fly deploy
```

CI/CD em `.github/workflows/`: `ci.yml` (valida imports + testes) + `deploy.yml` (fly deploy em push para `main`).

---

## Progresso

**§ US-01** Fundamentação ✅ · **US-02** Credenciamento ✅ · **US-03** RBAC ✅
**US-04** Trilhas ✅ · **US-05** Cursos avançado ✅ · **US-06** Upload/Gestão Conteúdos ✅

**31/72 tarefas do roadmap concluídas (43%).**
