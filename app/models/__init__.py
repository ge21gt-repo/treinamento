from app.models.avaliacao import Alternativa, Avaliacao, Questao, RespostaParticipante, ResultadoAvaliacao
from app.models.base import Base
from app.models.certificado import Certificado, ModeloCertificado
from app.models.comunicacao import ForumResposta, ForumTopico, MensagemChat
from app.models.conteudo import Conteudo, EntregaAtividade, MaterialComplementar
from app.models.credenciamento import AprovacaoHierarquica, SolicitacaoCredenciamento
from app.models.curso import (
    AulaSincrona,
    Curso,
    Inscricao,
    InscricaoTrilha,
    MensagemAula,
    MensagemCurso,
    Modulo,
    PresencaAula,
    ProgressoUnidade,
    TrilhaAprendizagem,
    Unidade,
)
from app.models.gamificacao import Badge, Missao, Nivel, PontosXP, Streak, UsuarioBadge, UsuarioMissao
from app.models.log import LogAcesso, LogAuditoria, MetricaEngajamento
from app.models.sandbox import SandboxSessao
from app.models.scorm import PacoteScorm, TrackingScorm
from app.models.sessao import Presenca, SessaoAoVivo
from app.models.token_reset import TokenResetSenha
from app.models.usuario import Perfil, Usuario, UsuarioPerfil

__all__ = [
    "Base",
    "Usuario",
    "Perfil",
    "UsuarioPerfil",
    "SolicitacaoCredenciamento",
    "AprovacaoHierarquica",
    "TrilhaAprendizagem",
    "Curso",
    "Modulo",
    "Unidade",
    "Inscricao",
    "ProgressoUnidade",
    "InscricaoTrilha",
    "AulaSincrona",
    "PresencaAula",
    "MensagemCurso",
    "MensagemAula",
    "Conteudo",
    "MaterialComplementar",
    "EntregaAtividade",
    "Avaliacao",
    "Questao",
    "Alternativa",
    "RespostaParticipante",
    "ResultadoAvaliacao",
    "Nivel",
    "PontosXP",
    "Badge",
    "UsuarioBadge",
    "Missao",
    "UsuarioMissao",
    "Streak",
    "SessaoAoVivo",
    "Presenca",
    "MensagemChat",
    "ForumTopico",
    "ForumResposta",
    "ModeloCertificado",
    "Certificado",
    "LogAcesso",
    "LogAuditoria",
    "MetricaEngajamento",
    "SandboxSessao",
    "PacoteScorm",
    "TrackingScorm",
    "TokenResetSenha",
]
