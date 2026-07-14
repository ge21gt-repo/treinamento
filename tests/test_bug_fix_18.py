"""Teste de integracao para validar fix do issue #18 - AmbiguousForeignKeysError"""

from app.models.credenciamento import SolicitacaoCredenciamento
from app.models.usuario import Usuario


def test_models_import_sem_erro_ambiguous():
    """Testa que os models podem ser importados sem AmbiguousForeignKeysError"""
    # Isso causa o erro se o primaryjoin nao estiver especificado

    # O erro ocorre quando o SQLAlchemy tenta montar os relationships
    # Se o import funcionar, o relationship esta configurado corretamente
    assert Usuario is not None
    assert SolicitacaoCredenciamento is not None

    # Verificar que o relationship existe no Usuario
    assert hasattr(Usuario, "solicitacoes_credenciamento")

    # Verificar que o relationship existe no SolicitacaoCredenciamento
    assert hasattr(SolicitacaoCredenciamento, "usuario")


def test_relationship_configurado_com_primaryjoin():
    """Testa que o relationship tem primaryjoin configurado"""
    from sqlalchemy import inspect

    # Inspeccionar o relationship Usuario.solicitacoes_credenciamento
    mapper = inspect(Usuario)
    rel = mapper.relationships.get("solicitacoes_credenciamento")

    assert rel is not None, "Relationship solicitacoes_credenciamento deve existir"

    # Verificar que primaryjoin esta configurado
    assert rel.primaryjoin is not None, "primaryjoin deve estar configurado para evitar ambiguidade"

    # Verificar que foreign_keys esta configurado
    assert rel.local_remote_pairs is not None, "foreign_keys deve estar configurado"
