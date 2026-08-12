-- Dedupe de inscricoes duplicadas (Issue 01)
-- Mantem a inscricao mais antiga de cada par (usuario_id, curso_id) e apaga as demais.
-- SAFE: roda em modo leitura primeiro (SELECT) — so executa o DELETE quando conferido.
--
-- Uso:  psql $DATABASE_URL -f scripts/dedupe_inscricoes.sql

-- 1. Conferir os duplicados antes de apagar
SELECT usuario_id, curso_id, count(*) AS qtd
FROM lms.inscricoes
GROUP BY usuario_id, curso_id
HAVING count(*) > 1
ORDER BY usuario_id, curso_id;

-- 2. Apagar as duplicadas, mantendo a de menor id (mais antiga)
DELETE FROM lms.inscricoes i
USING lms.inscricoes i2
WHERE i.usuario_id = i2.usuario_id
  AND i.curso_id = i2.curso_id
  AND i.id > i2.id;

-- 3. Conferir que nao restou nenhum par duplicado
SELECT count(*) AS duplicatas_restantes
FROM lms.inscricoes
GROUP BY usuario_id, curso_id
HAVING count(*) > 1;
