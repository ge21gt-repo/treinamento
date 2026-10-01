"""Testes unitarios de mascarar_cpf (issue #72 - LGPD)."""

from app.services.certificado_templates import mascarar_cpf


def test_mascarar_cpf_formato_padrao():
    assert mascarar_cpf("123.456.789-09") == "***.456.789-**"


def test_mascarar_cpf_sem_formatacao():
    assert mascarar_cpf("12345678909") == "***.456.789-**"


def test_mascarar_cpf_invalido_nao_vaza():
    # LGPD: nunca devolver CPF cru quando o formato e invalido
    assert mascarar_cpf("123") == "***"
    assert mascarar_cpf("abc") == "***"


def test_mascarar_cpf_vazio_none():
    assert mascarar_cpf("") == "-"
    assert mascarar_cpf(None) == "-"
