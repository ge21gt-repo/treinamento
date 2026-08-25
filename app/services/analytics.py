"""Analytics: coleta de metricas de engajamento (US-16, T-16.1)."""

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.avaliacao import ResultadoAvaliacao
from app.models.curso import MensagemCurso, ProgressoUnidade
from app.models.gamificacao import PontosXP
from app.models.log import LogAcesso, MetricaEngajamento
from app.models.curso import PresencaAula


async def coletar_metricas_diarias(db: AsyncSession, dia: date | None = None) -> int:
    """Agrega as metricas de engajamento de um dia (T-16.1).

    Calcula por usuario: conteudos/avaliacoes/mensagens/sessoes/xp do dia.
    Idempotente: se a linha do dia ja existe, substitui (nao duplica).
    Retorna a quantidade de usuarios agregados.
    """
    if dia is None:
        dia = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    inicio = datetime.combine(dia, time.min, tzinfo=timezone.utc)
    fim = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=timezone.utc)

    # usuarios com atividade no dia (login registrado)
    usuarios_ativos = (
        await db.execute(
            select(LogAcesso.usuario_id).where(
                LogAcesso.usuario_id.isnot(None),
                LogAcesso.criado_em >= inicio,
                LogAcesso.criado_em < fim,
            )
        )
    ).scalars().all()

    for uid in set(usuarios_ativos):
        await _agregar_usuario(db, uid, dia, inicio, fim)

    await db.flush()
    return len(set(usuarios_ativos))


async def _agregar_usuario(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    dia: date,
    inicio: datetime,
    fim: datetime,
) -> None:
    """Substitui a metrica do dia para um usuario (idempotente)."""
    antiga = await db.execute(
        select(MetricaEngajamento).where(
            MetricaEngajamento.usuario_id == usuario_id,
            MetricaEngajamento.data_referencia == dia,
        )
    )
    existente = antiga.scalar_one_or_none()
    if existente:
        await db.delete(existente)

    unidades = (
        await db.execute(
            select(func.count(ProgressoUnidade.id)).where(
                ProgressoUnidade.usuario_id == usuario_id,
                ProgressoUnidade.concluido_em >= inicio,
                ProgressoUnidade.concluido_em < fim,
            )
        )
    ).scalar() or 0

    avaliacoes = (
        await db.execute(
            select(func.count(ResultadoAvaliacao.id)).where(
                ResultadoAvaliacao.usuario_id == usuario_id,
                ResultadoAvaliacao.realizado_em >= inicio,
                ResultadoAvaliacao.realizado_em < fim,
            )
        )
    ).scalar() or 0

    mensagens = (
        await db.execute(
            select(func.count(MensagemCurso.id)).where(
                MensagemCurso.usuario_id == usuario_id,
                MensagemCurso.criado_em >= inicio,
                MensagemCurso.criado_em < fim,
            )
        )
    ).scalar() or 0

    sessoes = (
        await db.execute(
            select(func.count(PresencaAula.id)).where(
                PresencaAula.usuario_id == usuario_id,
                PresencaAula.hora_entrada >= inicio,
                PresencaAula.hora_entrada < fim,
            )
        )
    ).scalar() or 0

    xp = (
        await db.execute(
            select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(
                PontosXP.usuario_id == usuario_id,
                PontosXP.criado_em >= inicio,
                PontosXP.criado_em < fim,
            )
        )
    ).scalar() or 0

    db.add(
        MetricaEngajamento(
            usuario_id=usuario_id,
            data_referencia=dia,
            tempo_total_seg=0,  # sem tracking de tempo por sessao ainda
            conteudos_acessados=unidades,
            avaliacoes_realizadas=avaliacoes,
            mensagens_enviadas=mensagens,
            sessoes_assistidas=sessoes,
            xp_ganho=xp,
        )
    )


async def coletar_backlog(db: AsyncSession, dias: int = 30) -> int:
    """Coleta metricas dos ultimos N dias (para preencher o backlog)."""
    total = 0
    hoje = datetime.now(timezone.utc).date()
    for delta in range(1, dias + 1):
        dia = hoje - timedelta(days=delta)
        total += await coletar_metricas_diarias(db, dia)
    return total