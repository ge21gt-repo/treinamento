# Guia do Participante — Plataforma de Treinamento LMS

> US-20 / T-20.3 — Documentação baseada na API real do backend (v1).

## 1. Visão geral

Como **participante** (aluno), você pode:

- Realizar **cursos e trilhas** de treinamento
- Acompanhar seu **progresso** e **desempenho**
- Fazer **avaliações** e **entregas de atividades**
- Participar de **aulas ao vivo**, **chat** e **fórum**
- Ganhar **certificados** e pontos de **gamificação**

## 2. Primeiro acesso

O login é via **Keycloak** (identidade do IDESP). Ao acessar pela primeira vez:

- Sua conta é provisionada automaticamente com o perfil `participante`
- Você nasce como **pendente** — um administrador precisa **aprovar** seu acesso
- Até a aprovação, você **não consegue entrar** (aguarde o e-mail/aviso do admin)

## 3. Inscrição em cursos e trilhas

### 3.1 Curso

- Inscrever-se: `POST /api/v1/cursos/inscricoes`
- Ver minhas inscrições: `GET /api/v1/cursos/inscricoes/minhas`
- Cancelar inscrição: `DELETE /api/v1/cursos/inscricoes/{id}`

### 3.2 Trilha

- Inscrever-se: `POST /api/v1/trilhas/{trilha_id}/inscrever`
- Ver minhas trilhas: `GET /api/v1/trilhas/minhas-trilhas`
- Ver progresso da trilha: `GET /api/v1/trilhas/{trilha_id}/progresso`

## 4. Acompanhar progresso

- **Meu progresso geral**: `GET /api/v1/dashboard/meu-progresso`
- **Métricas de engajamento**: `GET /api/v1/dashboard/metricas/{usuario_id}`
- **Concluir unidade**: `POST /api/v1/cursos/unidades/{unidade_id}/concluir`

O progresso é calculado em **cascata**: unidade → curso → trilha. Conclua as
unidades de um curso para o progresso subir automaticamente.

## 5. Conteúdo e materiais

- **Player de vídeo**: `GET /api/v1/conteudos/{conteudo_id}/player`
- **Materiais complementares** ficam disponíveis no curso
- **SCORM**: execute pelo `GET /api/v1/scorm/{pacote_id}/launch`
- Conteúdos com `url_externa` abrem em nova aba (XR)

## 6. Avaliações

- Responder avaliação: `GET /api/v1/avaliacoes/{avaliacao_id}/responder`
- Submeter respostas: `POST /api/v1/avaliacoes/{avaliacao_id}/submeter`
- Ver meus resultados: `GET /api/v1/avaliacoes/meus-resultados`

**Tipos de questão:**
- Múltipla escolha — corrigida **automaticamente**
- Dissertativa — corrigida pelo **instrutor** (aguarde a correção)

## 7. Entregas de atividades

- Minhas entregas: `GET /api/v1/entregas/minhas`
- Entregas de uma unidade: `GET /api/v1/entregas/unidade/{unidade_id}`
- Enviar atividade: `POST /api/v1/entregas/upload` (upload de arquivo)

## 8. Aulas ao vivo e presença

- Próximas aulas: `GET /api/v1/cursos/aulas/proximas`
- Minhas presenças: `GET /api/v1/cursos/aulas/minhas-presencas`
- Entrar na aula: `POST /api/v1/cursos/aulas/{aula_id}/entrar`
- Acessar (abrir conteúdo): `POST /api/v1/cursos/aulas/{aula_id}/acessar`
- Sair: `POST /api/v1/cursos/aulas/{aula_id}/sair`

> Entrar na aula **não grava presença automaticamente**; a presença depende do
> tempo de permanência / registro do instrutor.

## 9. Chat e fórum

### 9.1 Chat do curso

- Enviar mensagem: `POST /api/v1/cursos/{curso_id}/chat`
- Ver mensagens: `GET /api/v1/cursos/{curso_id}/chat`
- Tempo real (SSE): `GET /api/v1/cursos/{curso_id}/chat/stream`

### 9.2 Fórum

- Tópicos do curso: `GET /api/v1/comunicacao/forum/{curso_id}`
- Criar tópico: `POST /api/v1/comunicacao/forum`
- Responder: `POST /api/v1/comunicacao/forum/respostas`

> Seja respeitoso: a moderação bloqueia termos ofensivos.

## 10. Gamificação

- **Meu perfil de gamificação**: `GET /api/v1/gamificacao/perfil`
- **Meus badges**: `GET /api/v1/gamificacao/badges/{usuario_id}`
- **Minhas missões**: `GET /api/v1/gamificacao/missoes/usuario/{usuario_id}`
- **Meu XP total**: `GET /api/v1/gamificacao/xp/{usuario_id}/total`
- **Minha posição no ranking**: `GET /api/v1/gamificacao/leaderboard/minha-posicao`
- **Meu streak**: `GET /api/v1/gamificacao/streaks/{usuario_id}`

Cada unidade concluída, avaliação respondida e atividade entregue gera **XP** e
pode render **badges** e subir de **nível**.

## 11. Certificados

- **Meus certificados**: `GET /api/v1/certificados/meus`
- Ver certificado: `GET /api/v1/certificados/{id}`
- Página pública de validação (sem login): `GET /api/v1/certificados/validar/{hash}/pagina`

Ao **concluir** um curso, o certificado é emitido **automaticamente** (mesmo sem
avaliação). Ele contém nome, CPF mascarado, prefeitura, curso, carga horária,
nota, data e um código de validação (hash).

## 12. Notificações

- Ver notificações: `GET /api/v1/notificacoes`
- Marcar como lida: `PATCH /api/v1/notificacoes/{id}/lida`
- Marcar todas como lidas: `POST /api/v1/notificacoes/marcar-todas-lidas`

Você recebe avisos de **aulas agendadas** e **gravação disponível**.

## 13. Dicas rápidas

1. Complete as unidades em ordem — o progresso é por módulo.
2. Faça as avaliações; as dissertativas dependem do instrutor.
3. Acompanhe **XP e streak** para manter o ritmo de estudo.
4. Guarde o **hash do certificado** para validar quando precisar.
5. Se ainda **pendente**, aguarde a aprovação do administrador para entrar.