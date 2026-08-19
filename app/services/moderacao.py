"""Servico de moderacao de conteudo do forum (US-14).

Termos bloqueados: default fixo no codigo + tabela forum_termos_bloqueados
(gerenciada pelo admin via API). O seed so popula se a tabela estiver vazia.
"""

import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comunicacao import ForumTermoBloqueado

TERMOS_DEFAULT: list[dict] = [
    {"termo": "eleicao", "categoria": "politico"},
    {"termo": "eleicoes", "categoria": "politico"},
    {"termo": "presidente", "categoria": "politico"},
    {"termo": "prefeito", "categoria": "politico"},
    {"termo": "governador", "categoria": "politico"},
    {"termo": "partido", "categoria": "politico"},
    {"termo": "candidato", "categoria": "politico"},
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


async def checar_conteudo(db: AsyncSession, texto: str) -> str | None:
    """Retorna o termo bloqueado encontrado, ou None se permitido."""
    normalizado = normalizar(texto)
    result = await db.execute(select(ForumTermoBloqueado).where(ForumTermoBloqueado.ativo.is_(True)))
    termos = result.scalars().all()
    for termo in termos:
        if normalizar(termo.termo) in normalizado:
            return termo.termo
    return None
