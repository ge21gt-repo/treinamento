"""Sistema de Controle de Acesso Baseado em Roles (RBAC)"""

# Constantes de permissão
class Permissoes:
    """Constantes de permissão do sistema"""
    AVALIACAO_CRIAR = "avaliacao:criar"
    AVALIACAO_RESPONDER = "avaliacao:responder"
    AVALIACAO_EDITAR = "avaliacao:editar"
    AVALIACAO_EXCLUIR = "avaliacao:excluir"
    AVALIACAO_VISUALIZAR = "avaliacao:visualizar"
    
    COMENTARIO_CRIAR = "comentario:criar"
    COMENTARIO_EDITAR = "comentario:editar"
    COMENTARIO_EXCLUIR = "comentario:excluir"
    COMENTARIO_VISUALIZAR = "comentario:visualizar"
    
    CURSO_CRIAR = "curso:criar"
    CURSO_EDITAR = "curso:editar"
    CURSO_EXCLUIR = "curso:excluir"
    CURSO_INSCREVER = "curso:inscrever"
    CURSO_INSCREVER_OUTROS = "curso:inscrever_outros"
    
    USUARIO_CRIAR = "usuario:criar"
    USUARIO_EDITAR = "usuario:editar"
    USUARIO_EXCLUIR = "usuario:excluir"
    USUARIO_LISTAR = "usuario:listar"
    
    RELATORIO_VISUALIZAR = "relatorio:visualizar"
    DASHBOARD_VISUALIZAR = "dashboard:visualizar"
    
    CREDENCIAMENTO_APROVAR = "credenciamento:aprovar"
    CREDENCIAMENTO_LISTAR = "credenciamento:listar"
    
    SANDBOX_TESTAR = "sandbox:testar"

    TRILHA_CRIAR = "trilha:criar"
    TRILHA_EDITAR = "trilha:editar"
    TRILHA_EXCLUIR = "trilha:excluir"
    TRILHA_INSCREVER = "trilha:inscrever"
    TRILHA_VER_PROGRESSO = "trilha:ver_progresso"

    CONTEUDO_CRIAR = "conteudo:criar"
    CONTEUDO_EDITAR = "conteudo:editar"
    CONTEUDO_EXCLUIR = "conteudo:excluir"
    CONTEUDO_VISUALIZAR = "conteudo:visualizar"

    MATERIAL_GERENCIAR = "material:gerenciar"

    ENTREGA_CRIAR = "entrega:criar"
    ENTREGA_VISUALIZAR = "entrega:visualizar"
    ENTREGA_CORRIGIR = "entrega:corrigir"

    SCORM_GERENCIAR = "scorm:gerenciar"
    SCORM_VISUALIZAR = "scorm:visualizar"


# Mapeamento de perfil → permissões (baseado na lógica de produto)
PERFIL_PERMISSOES = {
    "administrador_geral": [
        # Todas as permissões
        Permissoes.AVALIACAO_CRIAR, Permissoes.AVALIACAO_RESPONDER, Permissoes.AVALIACAO_EDITAR,
        Permissoes.AVALIACAO_EXCLUIR, Permissoes.AVALIACAO_VISUALIZAR,
        Permissoes.COMENTARIO_CRIAR, Permissoes.COMENTARIO_EDITAR, Permissoes.COMENTARIO_EXCLUIR,
        Permissoes.COMENTARIO_VISUALIZAR,
        Permissoes.CURSO_CRIAR, Permissoes.CURSO_EDITAR, Permissoes.CURSO_EXCLUIR,
        Permissoes.CURSO_INSCREVER, Permissoes.CURSO_INSCREVER_OUTROS,
        Permissoes.USUARIO_CRIAR, Permissoes.USUARIO_EDITAR, Permissoes.USUARIO_EXCLUIR,
        Permissoes.USUARIO_LISTAR,
        Permissoes.RELATORIO_VISUALIZAR, Permissoes.DASHBOARD_VISUALIZAR,
        Permissoes.CREDENCIAMENTO_APROVAR, Permissoes.CREDENCIAMENTO_LISTAR,
        Permissoes.SANDBOX_TESTAR,
        Permissoes.TRILHA_CRIAR, Permissoes.TRILHA_EDITAR, Permissoes.TRILHA_EXCLUIR,
        Permissoes.TRILHA_INSCREVER, Permissoes.TRILHA_VER_PROGRESSO,
        Permissoes.CONTEUDO_CRIAR, Permissoes.CONTEUDO_EDITAR, Permissoes.CONTEUDO_EXCLUIR, Permissoes.CONTEUDO_VISUALIZAR,
        Permissoes.MATERIAL_GERENCIAR,
        Permissoes.ENTREGA_VISUALIZAR, Permissoes.ENTREGA_CORRIGIR,
        Permissoes.SCORM_GERENCIAR, Permissoes.SCORM_VISUALIZAR,
    ],
    "administrador": [
        # Todas exceto auditoria (mesmo de admin_geral por enquanto)
        Permissoes.AVALIACAO_CRIAR, Permissoes.AVALIACAO_RESPONDER, Permissoes.AVALIACAO_EDITAR,
        Permissoes.AVALIACAO_EXCLUIR, Permissoes.AVALIACAO_VISUALIZAR,
        Permissoes.COMENTARIO_CRIAR, Permissoes.COMENTARIO_EDITAR, Permissoes.COMENTARIO_EXCLUIR,
        Permissoes.COMENTARIO_VISUALIZAR,
        Permissoes.CURSO_CRIAR, Permissoes.CURSO_EDITAR, Permissoes.CURSO_EXCLUIR,
        Permissoes.CURSO_INSCREVER, Permissoes.CURSO_INSCREVER_OUTROS,
        Permissoes.USUARIO_CRIAR, Permissoes.USUARIO_EDITAR, Permissoes.USUARIO_EXCLUIR,
        Permissoes.USUARIO_LISTAR,
        Permissoes.RELATORIO_VISUALIZAR, Permissoes.DASHBOARD_VISUALIZAR,
        Permissoes.CREDENCIAMENTO_APROVAR, Permissoes.CREDENCIAMENTO_LISTAR,
        Permissoes.SANDBOX_TESTAR,
        Permissoes.TRILHA_CRIAR, Permissoes.TRILHA_EDITAR, Permissoes.TRILHA_EXCLUIR,
        Permissoes.TRILHA_INSCREVER, Permissoes.TRILHA_VER_PROGRESSO,
        Permissoes.CONTEUDO_CRIAR, Permissoes.CONTEUDO_EDITAR, Permissoes.CONTEUDO_EXCLUIR, Permissoes.CONTEUDO_VISUALIZAR,
        Permissoes.MATERIAL_GERENCIAR,
        Permissoes.ENTREGA_VISUALIZAR, Permissoes.ENTREGA_CORRIGIR,
        Permissoes.SCORM_GERENCIAR, Permissoes.SCORM_VISUALIZAR,
    ],
    "instrutor": [
        # Pode criar/editar avaliações e comentários, cursos, sandbox
        Permissoes.AVALIACAO_CRIAR, Permissoes.AVALIACAO_RESPONDER, Permissoes.AVALIACAO_EDITAR,
        Permissoes.AVALIACAO_EXCLUIR, Permissoes.AVALIACAO_VISUALIZAR,
        Permissoes.COMENTARIO_CRIAR, Permissoes.COMENTARIO_EDITAR, Permissoes.COMENTARIO_EXCLUIR,
        Permissoes.COMENTARIO_VISUALIZAR,
        Permissoes.CURSO_CRIAR, Permissoes.CURSO_EDITAR, Permissoes.CURSO_EXCLUIR,
        Permissoes.CURSO_INSCREVER,
        Permissoes.SANDBOX_TESTAR,
        Permissoes.TRILHA_CRIAR, Permissoes.TRILHA_EDITAR, Permissoes.TRILHA_EXCLUIR,
        Permissoes.TRILHA_INSCREVER, Permissoes.TRILHA_VER_PROGRESSO,
        Permissoes.CONTEUDO_CRIAR, Permissoes.CONTEUDO_EDITAR, Permissoes.CONTEUDO_EXCLUIR, Permissoes.CONTEUDO_VISUALIZAR,
        Permissoes.MATERIAL_GERENCIAR,
        Permissoes.ENTREGA_VISUALIZAR, Permissoes.ENTREGA_CORRIGIR,
        Permissoes.SCORM_GERENCIAR, Permissoes.SCORM_VISUALIZAR,
    ],
    "auditor": [
        # Apenas visualização (relatórios, dashboards, avaliações, comentários, conteúdos)
        Permissoes.RELATORIO_VISUALIZAR, Permissoes.DASHBOARD_VISUALIZAR,
        Permissoes.AVALIACAO_VISUALIZAR, Permissoes.COMENTARIO_VISUALIZAR,
        Permissoes.CONTEUDO_VISUALIZAR,
        Permissoes.SCORM_VISUALIZAR,
    ],
    "gestor": [
        # Criar usuários (subordinados), inscrever outros, visualizar (mas não criar avaliações/comentários)
        Permissoes.USUARIO_CRIAR,
        Permissoes.CURSO_INSCREVER_OUTROS,
        Permissoes.RELATORIO_VISUALIZAR, Permissoes.DASHBOARD_VISUALIZAR,
        Permissoes.COMENTARIO_VISUALIZAR, Permissoes.AVALIACAO_VISUALIZAR,
        Permissoes.TRILHA_INSCREVER, Permissoes.TRILHA_VER_PROGRESSO,
        Permissoes.CONTEUDO_VISUALIZAR,
        Permissoes.ENTREGA_VISUALIZAR,
        Permissoes.SCORM_VISUALIZAR,
    ],
    "participante": [
        # Apenas inscrever em cursos, responder avaliações, visualizar
        Permissoes.CURSO_INSCREVER,
        Permissoes.AVALIACAO_RESPONDER, Permissoes.AVALIACAO_VISUALIZAR,
        Permissoes.COMENTARIO_VISUALIZAR,
        Permissoes.TRILHA_INSCREVER, Permissoes.TRILHA_VER_PROGRESSO,
        Permissoes.CONTEUDO_VISUALIZAR,
        Permissoes.ENTREGA_CRIAR, Permissoes.ENTREGA_VISUALIZAR,
        Permissoes.SCORM_VISUALIZAR,
    ],
}


def get_user_permissions(perfil_nome: str) -> list[str]:
    """
    Retorna a lista de permissões para um perfil específico
    conforme a lógica de produto definida
    """
    return PERFIL_PERMISSOES.get(perfil_nome, [])


def has_permission(perfil_nome: str, permissao: str) -> bool:
    """
    Verifica se um perfil tem uma permissão específica
    """
    permissoes = get_user_permissions(perfil_nome)
    return permissao in permissoes


def can_create_avaliacao(perfil_nome: str) -> bool:
    """Verifica se perfil pode criar avaliações (regra: gestor NÃO pode)"""
    return has_permission(perfil_nome, Permissoes.AVALIACAO_CRIAR)


def can_create_comentario(perfil_nome: str) -> bool:
    """Verifica se perfil pode criar comentários (regra: gestor NÃO pode)"""
    return has_permission(perfil_nome, Permissoes.COMENTARIO_CRIAR)


def can_use_sandbox(perfil_nome: str) -> bool:
    """Verifica se perfil pode usar sandbox (regra: apenas instrutor)"""
    return has_permission(perfil_nome, Permissoes.SANDBOX_TESTAR)
