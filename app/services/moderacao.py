"""Servico de moderacao de conteudo do forum (US-14).

Termos bloqueados: default fixo no codigo + tabela forum_termos_bloqueados
(gerenciada pelo admin via API). O seed so popula se a tabela estiver vazia.
"""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comunicacao import ForumTermoBloqueado

# Frases, nao palavras administrativas soltas: "presidente", "candidato", "partido",
# "eleicao"/"eleicoes" e "governador" bloqueavam vocabulario legitimo de servico publico
# (ex.: "presidente da comissao de licitacao", Lei 14.133) mesmo com casamento por
# palavra inteira, porque a palavra aparece sozinha nesses casos (issue 51).
TERMOS_DEFAULT: list[dict] = [
    {"termo": "campanha eleitoral", "categoria": "politico"},
    {"termo": "voto em", "categoria": "politico"},
    {"termo": "apoie o candidato", "categoria": "politico"},
    {"termo": "pornografia", "categoria": "improprio"},
    {"termo": "ofensa", "categoria": "improprio"},
    {"termo": "palavrao", "categoria": "improprio"},
]


def normalizar(texto: str) -> str:
    """Minusculas e sem acentos, para comparacao robusta."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower()


async def seed_termos_default(db: AsyncSession) -> None:
    """Popula termos default apenas se a tabela estiver vazia."""
    result = await db.execute(select(ForumTermoBloqueado.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return
    for item in TERMOS_DEFAULT:
        db.add(ForumTermoBloqueado(**item))
    await db.commit()


async def checar_conteudo(db: AsyncSession, texto: str) -> tuple[str, str | None] | None:
    """Retorna (termo, categoria) do termo bloqueado encontrado, ou None se permitido.

    Casa por palavra/frase inteira, nao por substring: "partido" nao deve recusar
    "repartido" nem "compartido" (issue 51).
    """
    normalizado = normalizar(texto)
    result = await db.execute(select(ForumTermoBloqueado).where(ForumTermoBloqueado.ativo.is_(True)))
    termos = result.scalars().all()
    for termo in termos:
        padrao = r"(?<!\w)" + re.escape(normalizar(termo.termo)) + r"(?!\w)"
        if re.search(padrao, normalizado):
            return termo.termo, termo.categoria
    return None
