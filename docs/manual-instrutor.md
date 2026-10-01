# Manual do Instrutor — Plataforma de Treinamento LMS

> US-20 / T-20.2 — Documentação baseada na API real do backend (v1).

## 1. Visão geral do papel

O **instrutor** cria e executa o conteúdo educacional da plataforma. Ele é
responsável por:

- Criar **cursos**, **módulos** e **unidades**
- **Publicar conteúdo** (vídeos, PDFs, SCORM, links externos)
- Criar **avaliações** (múltipla escolha e dissertativas)
- Acompanhar **entregas de atividades** e **corrigir**
- Conduzir **aulas síncronas** e ver **presença**
- Testar avaliações/comentários no **sandbox**

## 2. Hierarquia e credenciamento

O instrutor fica no nível hierárquico abaixo do administrador:

`administrador_geral` > `administrador` > **`instrutor`** > `gestor` > `participante`

O instrutor pode **aprovar solicitações** de perfis abaixo dele (gestor/participante).

## 3. Criação de cursos, módulos e unidades

### 3.1 Curso

- Criar: `POST /api/v1/cursos`
- Editar: `PATCH /api/v1/cursos/{curso_id}`
- Excluir: `DELETE /api/v1/cursos/{curso_id}`
- Campos típicos: título, descrição, carga horária, capa, instrutor, `publicado`

### 3.2 Módulos

- Criar: `POST /api/v1/cursos/modulos`
- Editar/excluir: `PATCH|DELETE /api/v1/cursos/modulos/{modulo_id}`
- Listar do curso: `GET /api/v1/cursos/{curso_id}/modulos`
- Reordenar: `PATCH /api/v1/cursos/modulos/reorder`

### 3.3 Unidades

- Criar: `POST /api/v1/cursos/unidades`
- Editar/excluir: `PATCH|DELETE /api/v1/cursos/unidades/{unidade_id}`
- Listar do módulo: `GET /api/v1/cursos/modulos/{modulo_id}/unidades`
- Reordenar: `PATCH /api/v1/cursos/unidades/reorder`

**Tipos de unidade:**
- `conteudo_url` — conteúdo interno (vídeo/PDF hospedado)
- `url_externa` — link externo (XR / redirecionamento)

### 3.4 Árvore de conteúdo

`GET /api/v1/cursos/{curso_id}/arvore` devolve a estrutura completa
(trilha → curso → módulos → unidades) para conferência antes de publicar.

## 4. Publicação de conteúdo multimídia

### 4.1 Upload (S3 ou disco local)

| Operação | Endpoint |
|---|---|
| Upload único | `POST /api/v1/conteudos/upload` (multipart) |
| Upload em partes (chunks) | `POST /conteudos/upload/iniciar`, `/chunk`, `/completar`, `/status` |
| Materiais complementares | `POST /conteudos/materiais/upload` |
| Gerenciar conteúdo | `GET/PATCH/DELETE /conteudos/{id}` |
| Player de vídeo | `GET /conteudos/{id}/player` |

Formatos suportados: vídeos (MP4), PDF, áudio, imagens, **SCORM**.

### 4.2 SCORM

- Upload: `POST /api/v1/scorm/upload`
- Launch (executar pacote): `GET /scorm/{pacote_id}/launch`
- Tracking (enviar/consultar): `GET|POST /scorm/{pacote_id}/tracking`
- Relatório por curso: `GET /scorm/cursos/{curso_id}/relatorio`

> O parsing do pacote SCORM é seguro contra XXE (`defusedxml`).

## 5. Aulas síncronas

Endpoints: `/api/v1/cursos/{curso_id}/aulas`

| Operação | Endpoint |
|---|---|
| Listar/criar aulas | `GET|POST /cursos/{curso_id}/aulas` |
| Editar/excluir | `PATCH|DELETE /cursos/aulas/{aula_id}` |
| Ver presença | `GET /cursos/aulas/{aula_id}/presencas` |
| Relatório de presença (CSV/PDF) | `GET /cursos/aulas/{aula_id}/presencas/relatorio?formato=csv\|pdf` |
| Processar gravação (Teams→S3) | `POST /cursos/aulas/{aula_id}/processar-gravacao` |

**Integração Teams:** é possível criar reunião via Microsoft Graph (`criar_reuniao_teams=true`).
Requer as variáveis `TEAMS_*` configuradas no ambiente e a Application Access Policy.
Sem essa infra, retorna 422 — use `link_externo` da reunião manual.

## 6. Avaliações

Endpoints: `/api/v1/avaliacoes`

| Operação | Endpoint |
|---|---|
| Criar avaliação | `POST /avaliacoes` |
| Editar/excluir | `PATCH|DELETE /avaliacoes/{id}` |
| Adicionar questão | `POST /avaliacoes/questoes` |
| Alternativas | `POST /avaliacoes/alternativas`, `PATCH/DELETE /alternativas/{id}` |
| Ver questões | `GET /avaliacoes/{id}/questoes` |
| Estatísticas | `GET /avaliacoes/{id}/estatisticas` |
| Correções pendentes | `GET /avaliacoes/correcoes-pendentes` |
| Corrigir resposta | `PATCH /avaliacoes/respostas/{id}/corrigir` |
| Resultados | `GET /avaliacoes/resultados/{usuario_id}` |

**Tipos de questão:** múltipla escolha (corrigida automaticamente) e
dissertativa (correção manual pelo instrutor).

## 7. Entregas de atividades

Endpoints: `/api/v1/entregas`

| Operação | Endpoint |
|---|---|
| Entregas de um usuário | `GET /entregas/usuario/{usuario_id}` |
| Entregas de uma unidade | `GET /entregas/unidade/{unidade_id}` |
| Ver entrega | `GET /entregas/{entrega_id}` |
| Corrigir entrega | `PATCH /entregas/{entrega_id}/corrigir` |

## 8. Sandbox do instrutor

Endpoints: `/api/v1/sandbox`

| Operação | Endpoint |
|---|---|
| Iniciar sessão | `POST /sandbox/iniciar` |
| Encerrar | `POST /sandbox/{sessao_id}/encerrar` |
| Sessão ativa | `GET /sandbox/ativo` |
| Listar sessões | `GET /sandbox/sessoes` |

O sandbox permite testar **avaliações e comentários** em ambiente controlado,
sem afetar turmas reais.

## 9. Chat, fórum e comunicação

### 9.1 Chat do curso

- Listar mensagens: `GET /cursos/{curso_id}/chat` (filtro `?usuario_id=`)
- Enviar: `POST /cursos/{curso_id}/chat`
- Streaming (SSE): `GET /cursos/{curso_id}/chat/stream`
- Moderar (silenciar/excluir): exige permissão `chat:moderar`

### 9.2 Chat da aula

- Enviar/listar: `GET|POST /cursos/aulas/{aula_id}/chat`
- Silenciar usuário: `PATCH /cursos/aulas/{aula_id}/chat/silenciar/{usuario_id}`
- Excluir mensagem: `DELETE /cursos/aulas/{aula_id}/chat/{mensagem_id}`

### 9.3 Fórum

Endpoints: `/api/v1/comunicacao/forum`

- Tópicos por curso: `GET /comunicacao/forum/{curso_id}`
- Criar tópico: `POST /comunicacao/forum`
- Respostas: `POST /comunicacao/forum/respostas`
- Fixar/fechar: `PATCH /forum/topico/{id}/fixar` e `/fechar`
- Termos bloqueados: `GET|POST /comunicacao/forum/termos-bloqueados`

> A moderação normaliza acentos e bloqueia termos ofensivos (422).

## 10. Trilhas de aprendizagem

Endpoints: `/api/v1/trilhas`

- Criar/editar/excluir trilhas: `POST|PATCH|DELETE /trilhas`
- Inscrever usuário: `POST /trilhas/{id}/inscrever`
- Progresso detalhado: `GET /trilhas/{id}/progresso-detalhado`
- Inscritos: `GET /trilhas/{id}/inscritos`

## 11. Dicas operacionais

1. **Publique o curso** apenas depois de validar a árvore de conteúdo.
2. Use **sandbox** para testar avaliações antes de aplicar na turma.
3. Para vídeos grandes, use **upload em partes** (chunks).
4. A **presença** da aula é a fonte oficial (`PresencaAula`); o endpoint legado `POST /sessoes/presenca` está deprecado.
5. Relatórios de presença podem ser exportados em **CSV ou PDF**.