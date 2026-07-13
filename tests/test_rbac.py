from app.services.rbac import PERFIL_PERMISSOES, Permissoes, has_permission


TODAS_PERMISSOES = [
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
]


def test_admin_criar_curso():
    assert has_permission("administrador_geral", Permissoes.CURSO_CRIAR)


def test_admin_criar_comentario():
    assert has_permission("administrador_geral", Permissoes.COMENTARIO_CRIAR)


def test_gestor_criar_curso():
    assert not has_permission("gestor", Permissoes.CURSO_CRIAR)


def test_participante_criar_curso():
    assert not has_permission("participante", Permissoes.CURSO_CRIAR)


def test_instrutor_avaliacao():
    assert has_permission("instrutor", Permissoes.AVALIACAO_CRIAR)


def test_gestor_avaliacao():
    assert not has_permission("gestor", Permissoes.AVALIACAO_CRIAR)


def test_participante_inscrever_trilha():
    assert has_permission("participante", Permissoes.TRILHA_INSCREVER)


def test_todas_permissoes_existem():
    assert Permissoes.CURSO_CRIAR == "curso:criar"
    assert Permissoes.CURSO_EDITAR == "curso:editar"
    assert Permissoes.CURSO_EXCLUIR == "curso:excluir"
    assert Permissoes.USUARIO_CRIAR == "usuario:criar"
    assert Permissoes.AVALIACAO_CRIAR == "avaliacao:criar"
    assert Permissoes.COMENTARIO_CRIAR == "comentario:criar"
    assert Permissoes.SANDBOX_TESTAR == "sandbox:testar"
    assert Permissoes.TRILHA_CRIAR == "trilha:criar"
    assert Permissoes.TRILHA_EDITAR == "trilha:editar"
    assert Permissoes.TRILHA_EXCLUIR == "trilha:excluir"
    assert Permissoes.TRILHA_INSCREVER == "trilha:inscrever"
    assert Permissoes.TRILHA_VER_PROGRESSO == "trilha:ver_progresso"


def test_administrador_geral_tem_tudo():
    permissoes = PERFIL_PERMISSOES["administrador_geral"]
    for permissao in TODAS_PERMISSOES:
        assert permissao in permissoes, f"admin_geral should have {permissao}"


def test_participante_permissoes_limitadas():
    permissoes = PERFIL_PERMISSOES["participante"]
    assert Permissoes.CURSO_CRIAR not in permissoes
    assert Permissoes.TRILHA_INSCREVER in permissoes
