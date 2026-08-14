from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.avaliacao import Alternativa, Avaliacao, Questao, RespostaParticipante


async def calcular_nota(
    db: AsyncSession,
    avaliacao: Avaliacao,
    questoes_ids: set[int],
    respostas_alternativas: dict[int, int | None],
    usuario_id=None,
    tentativa_num=None,
) -> tuple[Decimal, bool]:
    questoes = (
        await db.execute(
            select(Questao).where(Questao.avaliacao_id == avaliacao.id, Questao.id.in_(questoes_ids))
        )
    ).scalars().all()

    dissertativas_ids = [q.id for q in questoes if q.tipo == "dissertativa"]
    dissertativas_corrigidas: dict[int, RespostaParticipante] = {}
    if dissertativas_ids and usuario_id is not None and tentativa_num is not None:
        respostas_diss = (
            await db.execute(
                select(RespostaParticipante).where(
                    RespostaParticipante.usuario_id == usuario_id,
                    RespostaParticipante.tentativa_num == tentativa_num,
                    RespostaParticipante.questao_id.in_(dissertativas_ids),
                    RespostaParticipante.pontuacao_atribuida.is_not(None),
                )
            )
        ).scalars().all()
        dissertativas_corrigidas = {r.questao_id: r for r in respostas_diss}

    pontuacao_total = Decimal("0")
    pontuacao_obtida = Decimal("0")
    for q in questoes:
        if q.tipo == "dissertativa":
            corrigida = dissertativas_corrigidas.get(q.id)
            if corrigida is None:
                continue
            pontuacao_total += q.pontuacao
            pontuacao_obtida += corrigida.pontuacao_atribuida or Decimal("0")
            continue
        tem_alternativas = await db.scalar(
            select(func.count(Alternativa.id)).where(Alternativa.questao_id == q.id)
        )
        if not tem_alternativas:
            continue
        pontuacao_total += q.pontuacao
        alt_id = respostas_alternativas.get(q.id)
        if alt_id is not None:
            alt = await db.get(Alternativa, alt_id)
            if alt and alt.questao_id == q.id and alt.correta:
                pontuacao_obtida += q.pontuacao
    if pontuacao_total == 0:
        return (Decimal("0"), False)

    nota = (pontuacao_obtida / pontuacao_total) * Decimal("100")
    nota = nota.quantize(Decimal("0.01"))
    aprovado = nota >= avaliacao.nota_minima
    return (nota, aprovado)
