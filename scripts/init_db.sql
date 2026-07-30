-- Schema e extensoes
CREATE SCHEMA IF NOT EXISTS lms;
SET search_path TO lms, public;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

-- Seed: perfis padrao
INSERT INTO lms.perfis (nome, descricao) VALUES
    ('administrador_geral', 'Gerencia a plataforma, autoriza instrutores, controla permissoes e acessos, acompanha indicadores gerais, realiza auditorias'),
    ('administrador', 'Gestao de cursos e usuarios'),
    ('instrutor', 'Cria cursos, cria trilhas de aprendizagem, cria avaliacoes, gerencia conteudos, autoriza gestores'),
    ('auditor', 'Visualizacao de relatorios e dashboards'),
    ('gestor', 'Autoriza funcionarios, acompanha treinamentos, visualiza dashboards, emite relatorios, monitora desempenho da equipe'),
    ('participante', 'Participa de cursos e trilhas, realiza avaliacoes, acompanha seu progresso, emite certificados')
ON CONFLICT (nome) DO NOTHING;

-- Seed: niveis de gamificacao
INSERT INTO lms.niveis (nome, xp_minimo, ordem) VALUES
    ('Iniciante', 0, 1),
    ('Bronze', 500, 2),
    ('Prata', 1500, 3),
    ('Ouro', 3000, 4),
    ('Platina', 6000, 5),
    ('Diamante', 10000, 6),
    ('Mestre', 20000, 7)
ON CONFLICT (nome) DO NOTHING;

-- Indices de performance
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON lms.usuarios(email);
CREATE INDEX IF NOT EXISTS idx_inscricoes_usuario ON lms.inscricoes(usuario_id);
CREATE INDEX IF NOT EXISTS idx_inscricoes_curso ON lms.inscricoes(curso_id);
CREATE INDEX IF NOT EXISTS idx_progresso_usuario ON lms.progresso_unidade(usuario_id);
CREATE INDEX IF NOT EXISTS idx_pontos_xp_usuario ON lms.pontos_xp(usuario_id);
CREATE INDEX IF NOT EXISTS idx_presenca_sessao ON lms.presenca(sessao_id);
CREATE INDEX IF NOT EXISTS idx_log_acesso_usuario ON lms.log_acesso(usuario_id, criado_em);
CREATE INDEX IF NOT EXISTS idx_log_auditoria_tabela ON lms.log_auditoria(tabela_afetada, criado_em);
CREATE INDEX IF NOT EXISTS idx_metricas_data ON lms.metricas_engajamento(data_referencia);
CREATE INDEX IF NOT EXISTS idx_certificados_hash ON lms.certificados(hash_validacao);
CREATE INDEX IF NOT EXISTS idx_chat_sessao_tempo ON lms.mensagens_chat(sessao_id, enviado_em);
CREATE INDEX IF NOT EXISTS idx_streaks_usuario ON lms.streaks(usuario_id);
