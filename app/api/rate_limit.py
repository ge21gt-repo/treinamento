"""Shared rate limiter instance for the application.

O rate limit pode ser desligado via env `RATE_LIMIT_ENABLED=false` (usado no
teste de carga local, onde o limite por IP invalida a medicao). Em producao
permanece ativo (default `true`).
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/day", "50/hour"],
    enabled=settings.RATE_LIMIT_ENABLED,
)


def chave_por_token(request: Request) -> str:
    """Chave do limite: o token do portador; o IP so quando nao ha token.

    O default do projeto e por IP, e para as rotas de login e o certo. Para a
    rota de eventos de tour (issue #125) nao serve: atras do ingress um predio
    inteiro divide um IP, e 60 pedidos por minuto somados de todo mundo
    recusariam gente legitima. O token aproxima "por usuario" sem decodificar
    nada - e nao e garantia de identidade, mas aqui serve so para separar
    baldes, nao para autorizar.
    """
    cabecalho = request.headers.get("authorization") or ""
    if cabecalho.startswith("Bearer "):
        return cabecalho[7:]
    return get_remote_address(request)
