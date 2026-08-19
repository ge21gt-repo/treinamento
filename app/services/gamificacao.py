import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curso import Curso, Inscricao, InscricaoTrilha, ProgressoUnidade
from app.models.gamificacao import Badge, Missao, Nivel, PontosXP, Streak, UsuarioBadge, UsuarioMissao


EVENTOS_XP: dict[str, int] = {
    "unidade_concluida": 50,
    "curso_concluido": 200,
    "avaliacao_respondida": 30,
    "trilha_concluida": 500,
    "primeiro_acesso_dia": 5,
}


async def atribuir_xp(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    evento: str,
    descricao: str | None = None,
    referencia_id: int | None = None,
    quantidade: int | None = None,
) -> PontosXP | None:
    if quantidade is not None:
        quantidade_xp = quantidade
    elif evento == "login_streak":
        streak = await db.execute(select(Streak).where(Streak.usuario_id == usuario_id))
        s = streak.scalar_one_or_none()
        days = s.dias_consecutivos if s else 0
        quantidade_xp = 10 * days
    else:
        quantidade_xp = EVENTOS_XP.get(evento)
        if quantidade_xp is None:
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

    if quantidade_xp <= 0:
        return None

    pontos = PontosXP(
        usuario_id=usuario_id,
        quantidade=quantidade_xp,
        origem=evento,
        referencia_id=referencia_id,
        descricao=descricao,
    )
    db.add(pontos)
    await db.flush()

    await calcular_nivel(db, usuario_id)
    await verificar_badges(db, usuario_id)
    await atualizar_progresso_missoes(db, usuario_id)

    return pontos


async def calcular_nivel(db: AsyncSession, usuario_id: uuid.UUID) -> tuple[Nivel, Nivel | None]:
    total = await db.scalar(
        select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(PontosXP.usuario_id == usuario_id)
    )
    niveis = await db.execute(select(Nivel).order_by(Nivel.ordem.desc()))
    niveis_list = niveis.scalars().all()

    if not niveis_list:
        fallback = Nivel(nome="Iniciante", xp_minimo=0, ordem=0)
        return fallback, None

    nivel_atual = niveis_list[-1]
    proximo = None
    for n in niveis_list:
        if total >= n.xp_minimo:
            nivel_atual = n
            break

    acima = [n for n in niveis_list if n.xp_minimo > total]
    proximo = min(acima, key=lambda n: n.xp_minimo) if acima else None

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
        progresso = await calcular_progresso_criterio(db, usuario_id, badge.criterio_tipo)
        if progresso >= badge.criterio_valor:
            ub = UsuarioBadge(usuario_id=usuario_id, badge_id=badge.id)
            db.add(ub)
            concedidos.append(ub)

    if concedidos:
        await db.flush()

    return concedidos


async def calcular_progresso_criterio(db: AsyncSession, usuario_id: uuid.UUID, criterio_tipo: str) -> int:
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
                    ResultadoAvaliacao.nota >= 100,
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


async def atualizar_progresso_missoes(db: AsyncSession, usuario_id: uuid.UUID) -> list[UsuarioMissao]:
    """Atualiza o progresso das missoes do usuario (issue 21).

    Missoes ativas valem para todos automaticamente: cria a linha de
    usuario_missao quando ela ainda nao existe (PEND-25, decisao de produto).
    """
    hoje_d = date.today()
    missoes = await db.execute(select(Missao).where(Missao.ativa))
    missoes_list = [
        m
        for m in missoes.scalars().all()
        if (m.data_inicio is None or m.data_inicio <= hoje_d)
        and (m.data_fim is None or m.data_fim >= hoje_d)
    ]

    registros = await db.execute(
        select(UsuarioMissao).where(
            UsuarioMissao.usuario_id == usuario_id,
            UsuarioMissao.status == "em_andamento",
        )
    )
    ums = {um.missao_id: um for um in registros.scalars().all()}
    concluidas: list[UsuarioMissao] = []

    for missao in missoes_list:
        um = ums.get(missao.id)
        if um is None:
            um = UsuarioMissao(
                usuario_id=usuario_id,
                missao_id=missao.id,
                status="em_andamento",
                progresso_pct=Decimal("0.00"),
            )
            db.add(um)
            ums[missao.id] = um

        criterio = missao.criterio or {}
        criterio_tipo = criterio.get("criterio_tipo") or criterio.get("tipo")
        valor_alvo = criterio.get("valor") or criterio.get("criterio_valor")
        if criterio_tipo is None or valor_alvo is None or valor_alvo <= 0:
            continue

        progresso_atual = await calcular_progresso_criterio(db, usuario_id, criterio_tipo)
        pct = min(100, round(progresso_atual / valor_alvo * 100, 2))
        um.progresso_pct = Decimal(str(pct))

        if pct >= 100 and um.status == "em_andamento":
            um.status = "concluida"
            um.concluido_em = datetime.now()
            await db.flush()
            await atribuir_xp(
                db,
                usuario_id=usuario_id,
                evento="missao_concluida",
                descricao=f"Missão concluída: {missao.titulo}",
                referencia_id=missao.id,
                quantidade=missao.xp_recompensa,
            )
            concluidas.append(um)

    if concluidas or any(ums):
        await db.flush()

    return concluidas


async def atualizar_streak(db: AsyncSession, usuario_id: uuid.UUID) -> Streak:
    hoje = date.today()
    ref = hoje.toordinal()
    result = await db.execute(select(Streak).where(Streak.usuario_id == usuario_id))
    streak = result.scalar_one_or_none()

    if not streak:
        streak = Streak(
            usuario_id=usuario_id,
            dias_consecutivos=1,
            maior_streak=1,
            ultimo_acesso_dia=hoje,
        )
        db.add(streak)
        await db.flush()
        await atribuir_xp(db, usuario_id=usuario_id, evento="login_streak", referencia_id=ref)
        return streak

    if streak.ultimo_acesso_dia == hoje:
        return streak

    if streak.ultimo_acesso_dia == hoje - timedelta(days=1):
        streak.dias_consecutivos += 1
    else:
        streak.dias_consecutivos = 1

    streak.ultimo_acesso_dia = hoje
    if streak.dias_consecutivos > streak.maior_streak:
        streak.maior_streak = streak.dias_consecutivos

    await db.flush()
    await atribuir_xp(db, usuario_id=usuario_id, evento="login_streak", referencia_id=ref)
    return streak
