from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.avaliacao import Alternativa, Avaliacao, Questao


async def calcular_nota(
    db: AsyncSession,
    avaliacao: Avaliacao,
    questoes_ids: set[int],
    respostas_alternativas: dict[int, int | None],
) -> tuple[Decimal, bool]:
    questoes = (
        await db.execute(
            select(Questao).where(Questao.avaliacao_id == avaliacao.id, Questao.id.in_(questoes_ids))
        )
    ).scalars().all()

    pontuacao_total = sum(q.pontuacao for q in questoes)
    if pontuacao_total == 0:
        return (Decimal("0"), False)

    pontuacao_obtida = Decimal("0")
    for q in questoes:
        alt_id = respostas_alternativas.get(q.id)
        if alt_id is not None:
            alt = await db.get(Alternativa, alt_id)
            if alt and alt.questao_id == q.id and alt.correta:
                pontuacao_obtida += q.pontuacao

    nota = (pontuacao_obtida / pontuacao_total) * Decimal("100")
    nota = nota.quantize(Decimal("0.01"))
    aprovado = nota >= avaliacao.nota_minima
    return (nota, aprovado)
