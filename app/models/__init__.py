from app.models.base import Base
from app.models.usuario import Usuario, Perfil, UsuarioPerfil
from app.models.credenciamento import SolicitacaoCredenciamento, AprovacaoHierarquica
from app.models.curso import TrilhaAprendizagem, Curso, Modulo, Unidade, Inscricao, ProgressoUnidade, AulaSincrona, MensagemCurso, InscricaoTrilha
from app.models.conteudo import Conteudo, MaterialComplementar, EntregaAtividade
from app.models.avaliacao import Avaliacao, Questao, Alternativa, RespostaParticipante, ResultadoAvaliacao
from app.models.gamificacao import Nivel, PontosXP, Badge, UsuarioBadge, Missao, UsuarioMissao, Streak
from app.models.sessao import SessaoAoVivo, Presenca
from app.models.comunicacao import MensagemChat, ForumTopico, ForumResposta
from app.models.certificado import ModeloCertificado, Certificado
from app.models.log import LogAcesso, LogAuditoria, MetricaEngajamento
from app.models.sandbox import SandboxSessao
from app.models.scorm import PacoteScorm, TrackingScorm
from app.models.token_reset import TokenResetSenha

__all__ = [
    "Base",
    "Usuario", "Perfil", "UsuarioPerfil",
    "SolicitacaoCredenciamento", "AprovacaoHierarquica",
    "TrilhaAprendizagem", "Curso", "Modulo", "Unidade", "Inscricao", "ProgressoUnidade", "InscricaoTrilha",
    "AulaSincrona", "MensagemCurso",
    "Conteudo", "MaterialComplementar", "EntregaAtividade",
    "Avaliacao", "Questao", "Alternativa", "RespostaParticipante", "ResultadoAvaliacao",
    "Nivel", "PontosXP", "Badge", "UsuarioBadge", "Missao", "UsuarioMissao", "Streak",
    "SessaoAoVivo", "Presenca",
    "MensagemChat", "ForumTopico", "ForumResposta",
    "ModeloCertificado", "Certificado",
    "LogAcesso", "LogAuditoria", "MetricaEngajamento",
    "SandboxSessao",
    "PacoteScorm", "TrackingScorm",
    "TokenResetSenha",
]
