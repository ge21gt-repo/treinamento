"""Backfill da nota_final para inscricoes concluidas que ficaram com nota nula (issue 20).

Uso:
    python scripts/backfill_nota_final.py
"""

import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models.curso import Inscricao
from app.services.progresso import _nota_final_do_curso


async def main() -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Inscricao).where(
                Inscricao.status == "concluido",
                Inscricao.nota_final.is_(None),
            )
        )
        inscricoes = result.scalars().all()
        print(f"Encontradas {len(inscricoes)} inscricoes concluidas sem nota_final")

        atualizadas = 0
        for inc in inscricoes:
            nota = await _nota_final_do_curso(session, inc.usuario_id, inc.curso_id)
            if nota is not None:
                inc.nota_final = nota
                atualizadas += 1

        await session.commit()
        print(f"Atualizadas {atualizadas} inscricoes")


if __name__ == "__main__":
    asyncio.run(main())
