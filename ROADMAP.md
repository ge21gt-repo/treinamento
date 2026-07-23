# Roadmap de Implementação - Plataforma de Capacitação Governamental

Este documento contém todas as tarefas necessárias para transformar o LMS atual em uma plataforma de capacitação governamental com governança hierárquica, ordenadas da mais fácil para a mais complexa.

## ✅ CONCLUÍDAS - US-04 (Gestão de Trilhas)
- [x] US-04. Model InscricaoTrilha para rastrear matrícula/progresso em trilhas
- [x] US-04. Endpoints para inscrever usuário em trilha e listar progresso
- [x] US-04. Cálculo de progresso agregado da trilha (média dos cursos)
- [x] US-04. Permissões RBAC específicas para trilhas (trilha:criar, etc.)
- [x] US-04. Filtro por nível em GET /trilhas e filtro por trilha em GET /cursos

## ✅ CONCLUÍDAS - Pendências Técnicas (US-02/US-03)
- [x] T-02.5. Recuperação de senha (esqueci-senha + redefinir-senha + email service)
- [x] T-02.6. LGPD (aceite_lgpd validation)
- [x] T-02.7. Testes de autenticação (8 testes)
- [x] T-03.1. CRUD perfis completo (PATCH/DELETE)
- [x] T-03.7. Testes RBAC (10 testes)

## ✅ CONCLUÍDAS - US-05 (Gestão de Cursos, Módulos e Unidades)
- [x] US-05. Sub-módulos tipados (conteudo_url, url_externa na Unidade)
- [x] US-05. Aulas síncronas (CRUD + GET /aulas/proximas)
- [x] US-05. Chat contínuo por curso (POST/GET + SSE streaming)
- [x] US-05. Reordenação módulos/unidades (PATCH reorder)
- [x] US-05. Pré-requisitos (validação existência + ciclo + bloqueio inscrição)
- [x] US-05. Árvore de conteúdo (GET /cursos/{id}/arvore)
- [x] US-05. XR (url_externa)
- [x] US-05. Testes US-05 (11 testes)

## 🟢 FÁCEIS - Ajustes e Melhorias Imediatas

- [x] 1. Ajustar seeds de perfis para incluir perfil 'gestor' e ajustar descrições existentes
- [x] 2. Criar schemas Pydantic para Gestor (GestorCreate, GestorRead, etc.)
- [x] 3. Adicionar endpoint para listar usuários por perfil (filtrar gestores, instrutores, etc.) ✅
- [ ] 4. Implementar endpoint de horas de capacitação por usuário (consolidar carga_horaria dos cursos concluídos)
- [ ] 5. Criar view SQL ou query para métricas de horas por órgão/instituição
- [ ] 6. Adicionar filtros por perfil no endpoint /dashboard/resumo
- [ ] 7. Implementar endpoint de relatório simples por servidor (lista cursos, progresso, horas)
- [ ] 8. Implementar endpoint de relatório por curso (inscritos, concluintes, média, horas totais)
- [ ] 9. Adicionar exportação CSV nos endpoints de relatórios existentes

## 🟡 MÉDIAS - Estrutura Organizacional

- [ ] 10. Criar tabela de estrutura organizacional (estados, municipios, secretarias, unidades_administrativas)
- [ ] 11. Criar migrations para tabelas organizacionais
- [ ] 12. Adicionar campos em Usuario para vincular à estrutura organizacional (estado_id, municipio_id, secretaria_id, unidade_id)
- [ ] 13. Criar schemas para estrutura organizacional (Estado, Municipio, Secretaria, Unidade)
- [ ] 14. Implementar CRUD básico para estrutura organizacional (estados, municípios, secretarias, unidades)
- [ ] 15. Atualizar endpoint de registro para incluir campos organizacionais
- [ ] 16. Criar tabela de relacionamento gestor-funcionário (gestor_subordinado)
- [ ] 17. Implementar endpoint para gestor listar seus subordinados
- [x] 17.1. Criar endpoint para gestor criar conta de participante (subordinado) ✅

## 🟠 MÉDIAS-ALTAS - Controle de Acesso e Credenciamento

- [x] 17.2. Implementar sistema de permissões granular baseado em hierarquia (RBAC) [movido de #55] ✅
- [x] 17.3. Criar middleware para verificar permissões baseadas em hierarquia [movido de #56] ✅

- [x] 18. Criar tabela de solicitações de credenciamento (solicitacoes_credenciamento) ✅ estrutura
- [x] 19. Criar schema para SolicitacaoCredenciamento (Create, Read, Update status) ✅ estrutura
- [x] 20. Modificar endpoint /auth/registro para não criar usuário ativo, mas criar solicitação pendente ✅
- [x] 21. Implementar endpoint para listar solicitações pendentes (por gestor/admin) ✅
- [x] 22. Implementar endpoint para aprovar/rejeitar solicitação de credenciamento ✅
- [x] 23. Adicionar campos em Usuario para rastrear quem aprovou (aprovado_por, data_aprovacao) ✅ estrutura
- [x] 24. Implementar middleware/dependency para verificar se usuário está credenciado antes de permitir acesso ✅
- [x] 25. Criar tabela de aprovacoes_hierarquicas para rastreabilidade completa ✅ estrutura
- [x] 26. Implementar lógica de autorização hierárquica (Admin aprova Instrutor, Instrutor aprova Gestor, Gestor aprova Funcionário) ✅
- [ ] 27. Modificar endpoint de inscrição em curso para exigir aprovação do gestor
- [ ] 28. Criar tabela de solicitacoes_matricula (usuario, curso, gestor_responsavel, status)
- [ ] 29. Implementar endpoint para funcionário solicitar matrícula em curso
- [ ] 30. Implementar endpoint para gestor aprovar/rejeitar matrícula de subordinado
- [x] 30.1. Implementar modo sandbox para instrutor testar avaliações, comentários e interações sem efeito real ✅

## 🔴 ALTAS - Dashboards e Relatórios

- [ ] 31. Criar dashboard específico para Gestor (subordinados, matrículas pendentes, progresso da equipe, horas da equipe)
- [ ] 32. Criar dashboard específico para Instrutor (cursos, participantes, conclusões, desempenho)
- [ ] 33. Criar dashboard específico para Administrador Geral (métricas globais, por órgão, por município)
- [ ] 34. Implementar relatório consolidado por município (servidores, horas, conclusões)
- [ ] 35. Implementar relatório consolidado por secretaria (servidores, horas, conclusões)
- [ ] 36. Implementar relatório consolidado por trilha (participantes, conclusões, horas totais)
- [ ] 37. Adicionar exportação PDF nos relatórios (implementar geração de PDF)
- [ ] 38. Adicionar exportação XLSX nos relatórios (implementar geração de Excel)

## 🔴 MUITO ALTAS - Integrações e Notificações

- [ ] 39. Implementar sistema de notificações (tabela notificacoes, status lido/não lido)
- [ ] 40. Criar endpoint para listar notificações do usuário
- [ ] 41. Integrar notificações no fluxo de aprovação (notificar usuário quando aprovado/rejeitado)
- [ ] 42. Integrar notificações no fluxo de matrícula (notificar gestor sobre solicitação, funcionário sobre decisão)
- [ ] 43. Enriquecer log_auditoria com mais contexto (motivo, hierarquia, etc.)
- [ ] 44. Criar tabela historico_status_usuario para rastrear mudanças de status
- [ ] 45. Implementar endpoint para auditoria de aprovações (quem aprovou quem, quando, por qual motivo)

## 🟣 MUITO COMPLEXAS - Integrações Externas

- [ ] 46. Criar módulo de integrações externas (tabela integracoes, configuracoes)
- [ ] 47. Criar tabela para provedores externos (nome, tipo, api_endpoint, autenticacao_config)
- [ ] 48. Implementar endpoints CRUD para gerenciar provedores externos
- [ ] 49. Criar tabela de treinamentos_externos (usuario, provedor_id, curso_externo_id, status, data_conclusao)
- [ ] 50. Implementar cliente HTTP genérico para integrações (base httpx já existe)
- [ ] 51. Implementar endpoint para redirecionar usuário para plataforma externa (gerar link/token)
- [ ] 52. Implementar webhook endpoint para receber notificações da plataforma RV (conclusão, progresso)
- [ ] 53. Implementar serviço de sincronização de dados externos (buscar cursos, progresso da plataforma RV)
- [ ] 54. Criar jobs/tarefas agendadas para sincronização periódica com plataformas externas

## 🟣 EXTREMAMENTE COMPLEXAS - Arquitetura Avançada

- [ ] 55. Implementar cache de métricas para dashboards (Redis ou similar)
- [ ] 56. Criar dashboard analítico avançado com gráficos e filtros complexos
- [ ] 57. Implementar sistema de busca avançada (por órgão, cargo, período, etc.)
- [ ] 58. Criar API de relatórios dinâmicos (usuário monta seu próprio relatório)

---

## Legenda de Status

- [ ] **Pendente** - Tarefa ainda não iniciada
- [x] **Concluída** - Tarefa finalizada e testada

## Estatísticas

- **Total de tarefas**: 72
- **Concluídas**: 23 (tasks 1-3, 17.1-17.3, 18-26, 30.1 + US-04 + T-02.5/2.6/2.7 + T-03.1/3.7 + US-05)
- **Pendentes**: 49
- **Progresso**: 31.9%

## Notas

- As tarefas estão ordenadas por complexidade crescente
- Tarefas anteriores podem ser pré-requisitos para tarefas posteriores
- Cada tarefa deve ser testada individualmente antes de prosseguir
- Issues no GitHub podem ser criadas para cada tarefa ou grupo de tarefas
