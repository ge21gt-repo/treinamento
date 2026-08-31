# Quality Gate + Ratchet Pattern + Agentic Feedback Loop (IDEIA - nao implementada)

> Status: PROPOSTA guardada para avaliacao futura. NAO commitado.
> Data: 19/08/2026

## Conceito recebido (resumo)
Implementar Quality Gate com Ratchet Pattern (regra da catraca: nunca regressao vs baseline)
e Agentic Feedback Loop (auto-babysitting do agente OpenCode).

## Analise feita em 19/08/2026

### Vale a pena agora (custo baixo, ganho real)
1. Corrigir AGENTS.md desatualizado (diz "no linter config" mas CI ja roda ruff).
2. Adicionar `pytest-cov` ao requirements + cobertura como relatorio no CI (sem gate).
3. Instrucao de babysitting com teto no AGENTS.md (max 3 tentativas; parar em flake).

### Adiar (so quando o ritmo estabilizar / apos issues 17-24)
4. `scripts/quality_gate.py` + `baseline.json` (ratchet).
   - Regra: ruff check --output-format=json + pytest --cov + count .py >500 linhas.
   - Ler/criar baseline.json; regressao -> exit 1; igual/melhor -> atualiza baseline, exit 0.
   - Gerar quality_summary.md.
   - CRITICO: baseline DEVE nascer no CI (local usa banco externo lms_idesp_teste,
     CI usa servico postgres:15 -> cobertura difere -> falso-positivo).
   - NAO duplicar ci.yml (ja roda ruff + pytest em PR para main). Integrar, nao criar workflow novo.
5. Regra de 500 linhas: cursos.py (1439) e avaliacoes.py (1036) ja estouram hoje.
   Preferir complexidade ciclomatica (ruff C901) ou aceitar gigantes no baseline.

### Naooo vale (agora)
6. Workflow separado quality_gate.yml (duplicaria ci.yml).
7. Baseline gerado localmente (falso-positivo vs CI).
8. pytest --cov no loop local do agente (testes 5-25min -> inviavel por tarefa).

## Decisao
- Babysitting: SIM agora (formalizar no AGENTS.md com teto).
- Ratchet/gate duro: ADIAR ate as issues 17-24 terminarem e o projeto estabilizar.
- Feedback loop com 3 travas: teto de iteracoes, nao corrigir flake, gate leve local.
