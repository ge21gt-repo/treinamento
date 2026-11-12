"""Issue #129 — `POST /auth/redefinir-senha` nunca encontrava o token
(`WHERE false`) e o link de reset, com o token dentro, ia para o log quando o
SMTP falhava.
"""

import pytest
from fastapi import status

from app.api import auth as auth_module
from app.services import email as email_module

_EMAIL = "admin@test.com"
_SENHA_NOVA = "NovaSenha#129"


@pytest.fixture
def anonimo(client):
    """Rotas de /auth são públicas: sem Bearer, para não disparar o log_acesso.

    A task de log_acesso sobrevive ao teste e segura `lms.log_acesso`, travando
    o TRUNCATE do `db_clean` seguinte (ver AGENTS.md).
    """
    client.headers.pop("Authorization", None)
    return client


def _capturar_link(monkeypatch) -> dict:
    capturado: dict = {}

    def fake_enviar(destino, nome, link):
        capturado["destino"] = destino
        capturado["link"] = link
        return True

    monkeypatch.setattr(auth_module, "send_reset_email", fake_enviar)
    return capturado


def _token_do_link(link: str) -> str:
    assert "token=" in link, f"link sem token: {link!r}"
    return link.split("token=", 1)[1]


async def test_redefinir_senha_encontra_token_e_troca_a_senha(anonimo, monkeypatch):
    capturado = _capturar_link(monkeypatch)

    r = await anonimo.post("/api/v1/auth/esqueci-senha", json={"email": _EMAIL})
    assert r.status_code == status.HTTP_200_OK, r.text
    token = _token_do_link(capturado["link"])

    r = await anonimo.post(
        "/api/v1/auth/redefinir-senha",
        json={"token": token, "nova_senha": _SENHA_NOVA},
    )
    assert r.status_code == status.HTTP_200_OK, r.text

    # A senha nova precisa valer no login local.
    r = await anonimo.post("/api/v1/auth/login", json={"email": _EMAIL, "senha": _SENHA_NOVA})
    assert r.status_code == status.HTTP_200_OK, r.text


async def test_token_de_reset_nao_pode_ser_reutilizado(anonimo, monkeypatch):
    capturado = _capturar_link(monkeypatch)

    await anonimo.post("/api/v1/auth/esqueci-senha", json={"email": _EMAIL})
    token = _token_do_link(capturado["link"])

    primeira = await anonimo.post(
        "/api/v1/auth/redefinir-senha",
        json={"token": token, "nova_senha": _SENHA_NOVA},
    )
    assert primeira.status_code == status.HTTP_200_OK, primeira.text

    segunda = await anonimo.post(
        "/api/v1/auth/redefinir-senha",
        json={"token": token, "nova_senha": "Outra#129"},
    )
    assert segunda.status_code == status.HTTP_400_BAD_REQUEST, segunda.text


def test_falha_de_smtp_nao_escreve_o_link_no_log(monkeypatch):
    linhas: list[str] = []

    class _LoggerEspiao:
        def info(self, msg, *args, **kwargs):
            linhas.append(str(msg) % args if args else str(msg))

        def warning(self, msg, *args, **kwargs):
            linhas.append(str(msg) % args if args else str(msg))

        def error(self, msg, *args, **kwargs):
            linhas.append(str(msg) % args if args else str(msg))

    class _SMTPIndisponivel:
        def __init__(self, *args, **kwargs):
            raise OSError("SMTP indisponivel")

    monkeypatch.setattr(email_module, "logger", _LoggerEspiao())
    monkeypatch.setattr(email_module.smtplib, "SMTP", _SMTPIndisponivel)

    ok = email_module.send_reset_email(
        _EMAIL, "Admin", "https://exemplo/auth/redefinir-senha?token=SEGREDO123"
    )

    assert ok is False
    texto = "\n".join(linhas)
    assert "SEGREDO123" not in texto
    assert "token=" not in texto
