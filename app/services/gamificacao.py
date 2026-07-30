import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curso import Curso, Inscricao, InscricaoTrilha, ProgressoUnidade
from app.models.gamificacao import Badge, Nivel, PontosXP, Streak, UsuarioBadge


EVENTOS_XP: dict[str, int] = {
    "unidade_concluida": 50,
    "curso_concluido": 200,
    "avaliacao_respondida": 30,
    "trilha_concluida": 500,
    "login_streak": 10,
    "primeiro_acesso_dia": 5,
}


async def atribuir_xp(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    evento: str,
    descricao: str | None = None,
    referencia_id: int | None = None,
) -> PontosXP | None:
    quantidade = EVENTOS_XP.get(evento)
    if quantidade is None:
        raise ValueError(f"Evento desconhecido: {evento}")

    if referencia_id is not None:
        existente = await db.execute(
            select(PontosXP).where(
                PontosXP.usuario_id == usuario_id,
                PontosXP.origem == evento,
                PontosXP.referencia_id == referencia_id,
            )
        )
        if existente.scalar_one_or_none():
            return None

    pontos = PontosXP(
        usuario_id=usuario_id,
        quantidade=quantidade,
        origem=evento,
        referencia_id=referencia_id,
        descricao=descricao,
    )
    db.add(pontos)
    await db.flush()

    return pontos


async def _calcular_nivel(db: AsyncSession, usuario_id: uuid.UUID) -> tuple[Nivel, Nivel | None]:
    total = await db.scalar(
        select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(PontosXP.usuario_id == usuario_id)
    )
    niveis = await db.execute(select(Nivel).order_by(Nivel.ordem.desc()))
    niveis_list = niveis.scalars().all()

    nivel_atual = niveis_list[-1]
    proximo = None
    for n in niveis_list:
        if total >= n.xp_minimo:
            nivel_atual = n
            break

    for n in niveis_list:
        if n.xp_minimo > total:
            proximo = n
            break

    return nivel_atual, proximo


async def verificar_badges(db: AsyncSession, usuario_id: uuid.UUID) -> list[UsuarioBadge]:
    badges = await db.execute(
        select(Badge).where(
            Badge.ativo,
            Badge.id.not_in(
                select(UsuarioBadge.badge_id).where(UsuarioBadge.usuario_id == usuario_id)
            ),
        )
    )
    badges_list = badges.scalars().all()
    concedidos: list[UsuarioBadge] = []

    for badge in badges_list:
        progresso = await _calcular_progresso_criterio(db, usuario_id, badge.criterio_tipo)
        if progresso >= badge.criterio_valor:
            ub = UsuarioBadge(usuario_id=usuario_id, badge_id=badge.id)
            db.add(ub)
            concedidos.append(ub)

    if concedidos:
        await db.flush()

    return concedidos


async def _calcular_progresso_criterio(db: AsyncSession, usuario_id: uuid.UUID, criterio_tipo: str) -> int:
    match criterio_tipo:
        case "cursos_concluidos":
            return await db.scalar(
                select(func.count(Inscricao.id)).where(
                    Inscricao.usuario_id == usuario_id,
                    Inscricao.status == "concluido",
                )
            ) or 0
        case "unidades_concluidas":
            return await db.scalar(
                select(func.count(ProgressoUnidade.id)).where(
                    ProgressoUnidade.usuario_id == usuario_id,
                    ProgressoUnidade.status == "concluido",
                )
            ) or 0
        case "xp_acumulado":
            return await db.scalar(
                select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(PontosXP.usuario_id == usuario_id)
            ) or 0
        case "dias_streak":
            streak = await db.execute(select(Streak).where(Streak.usuario_id == usuario_id))
            s = streak.scalar_one_or_none()
            return s.maior_streak if s else 0
        case "avaliacoes_perfeitas":
            from app.models.avaliacao import ResultadoAvaliacao
            return await db.scalar(
                select(func.count(ResultadoAvaliacao.id)).where(
                    ResultadoAvaliacao.usuario_id == usuario_id,
                    ResultadoAvaliacao.nota >= 10,
                )
            ) or 0
        case "trilhas_concluidas":
            return await db.scalar(
                select(func.count(InscricaoTrilha.id)).where(
                    InscricaoTrilha.usuario_id == usuario_id,
                    InscricaoTrilha.status == "concluido",
                )
            ) or 0
        case _:
            return 0
