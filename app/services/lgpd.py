"""Aceite do termo de uso e da politica de privacidade (issue #119).

A regra de "falta aceitar" vive aqui porque tres lugares precisam dela e
precisam concordar: a rota do aceite, o bloqueio em get_current_user e o campo
que o front le em /usuarios/me. Duas copias divergiriam na primeira mudanca.
"""

from app.config import settings

# Issue #119, item 4: o que continua acessivel enquanto o aceite esta pendente.
# Comparado por sufixo porque o caminho que chega aqui carrega o ROOT_PATH e o
# prefixo /api/v1.
ROTAS_LIBERADAS = (
    "/usuarios/me",
    "/usuarios/me/aceite-lgpd",
    "/auth/logout",
)


def aceite_pendente(aceite_lgpd: bool, versao_aceita: str | None) -> bool:
    """Diz se a pessoa ainda precisa aceitar o termo em vigor.

    Pendente em dois casos: nunca aceitou, ou aceitou uma versao diferente da
    que esta em vigor. O segundo caso e o que faz o re-aceite decidido em
    produto valer para quem ja existia: as linhas antigas tem
    `versao_termo_lgpd` nulo, que nunca casa com a versao atual, e ninguem
    precisa apagar `aceite_lgpd` nem a data do aceite anterior para isso.
    """
    if not aceite_lgpd:
        return True
    return (versao_aceita or "") != settings.VERSAO_TERMO_LGPD


def rota_liberada(caminho: str) -> bool:
    """Diz se o caminho continua acessivel com o aceite pendente."""
    limpo = caminho.rstrip("/")
    return any(limpo.endswith(rota) for rota in ROTAS_LIBERADAS)
