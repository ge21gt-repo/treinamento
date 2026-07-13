from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.curso import Curso, Inscricao, InscricaoTrilha, Modulo, ProgressoUnidade, Unidade


async def _get_unidade_curso(db: AsyncSession, unidade_id: int) -> tuple[int, int | None]:
    """Retorna (curso_id, trilha_id) para uma unidade."""
    result = await db.execute(
        select(Modulo).where(Modulo.id == Unidade.modulo_id)
        .options(selectinload(Modulo.curso))
    )
    # mais simples: busca via join direto
    result = await db.execute(
        select(Curso.id, Curso.trilha_id)
        .select_from(Unidade)
        .join(Modulo, Modulo.id == Unidade.modulo_id)
        .join(Curso, Curso.id == Modulo.curso_id)
        .where(Unidade.id == unidade_id)
    )
    row = result.one_or_none()
    if not row:
        raise ValueError("Unidade nao encontrada")
    return row._mapping["id"], row._mapping.get("trilha_id")


async def concluir_unidade(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    unidade_id: int,
    tempo_gasto: int = 0,
) -> ProgressoUnidade:
    now = datetime.now(timezone.utc)
    curso_id, _ = await _get_unidade_curso(db, unidade_id)
    insc = await db.execute(
        select(Inscricao).where(
            Inscricao.usuario_id == usuario_id,
            Inscricao.curso_id == curso_id,
        )
    )
    if not insc.scalar_one_or_none():
        raise ValueError("Usuario nao inscrito neste curso")
    result = await db.execute(
        select(ProgressoUnidade).where(
            ProgressoUnidade.usuario_id == usuario_id,
            ProgressoUnidade.unidade_id == unidade_id,
        )
    )
    progresso = result.scalar_one_or_none()
    if progresso:
        progresso.status = "concluido"
        progresso.concluido_em = now
        if tempo_gasto:
            progresso.tempo_gasto = progresso.tempo_gasto + tempo_gasto
    else:
        progresso = ProgressoUnidade(
            usuario_id=usuario_id,
            unidade_id=unidade_id,
            status="concluido",
            tempo_gasto=tempo_gasto,
            concluido_em=now,
        )
        db.add(progresso)

    await db.flush()

    curso_id, trilha_id = await _get_unidade_curso(db, unidade_id)

    if curso_id:
        await atualizar_progresso_curso(db, usuario_id, curso_id)

        if trilha_id:
            await atualizar_progresso_trilha(db, usuario_id, trilha_id)

    return progresso


async def atualizar_progresso_curso(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    curso_id: int,
) -> Inscricao:
    total = await db.execute(
        select(func.count(Unidade.id))
        .select_from(Curso)
        .join(Modulo, Modulo.curso_id == Curso.id)
        .join(Unidade, Unidade.modulo_id == Modulo.id)
        .where(Curso.id == curso_id)
    )
    total_unidades = total.scalar() or 0

    concluidas = await db.execute(
        select(func.count(ProgressoUnidade.id))
        .where(
            ProgressoUnidade.usuario_id == usuario_id,
            ProgressoUnidade.unidade_id.in_(
                select(Unidade.id)
                .select_from(Curso)
                .join(Modulo, Modulo.curso_id == Curso.id)
                .join(Unidade, Unidade.modulo_id == Modulo.id)
                .where(Curso.id == curso_id)
            ),
            ProgressoUnidade.status == "concluido",
        )
    )
    qtd_concluidas = concluidas.scalar() or 0

    pct = Decimal("0.00")
    if total_unidades > 0:
        pct = Decimal(str(round((qtd_concluidas / total_unidades) * 100, 2)))

    result = await db.execute(
        select(Inscricao).where(
            Inscricao.usuario_id == usuario_id,
            Inscricao.curso_id == curso_id,
        )
    )
    inscricao = result.scalar_one_or_none()
    if inscricao:
        inscricao.progresso_pct = pct
        if pct >= 100:
            inscricao.status = "concluido"
            if not inscricao.data_conclusao:
                inscricao.data_conclusao = datetime.now(timezone.utc)
        elif inscricao.status == "concluido" and pct < 100:
            inscricao.status = "inscrito"

    await db.flush()
    return inscricao


async def atualizar_progresso_trilha(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    trilha_id: int,
) -> InscricaoTrilha:
    cursos = await db.execute(
        select(Curso.id).where(Curso.trilha_id == trilha_id)
    )
    curso_ids = [row[0] for row in cursos.all()]
    if not curso_ids:
        return None

    inscricoes = await db.execute(
        select(Inscricao.progresso_pct).where(
            Inscricao.usuario_id == usuario_id,
            Inscricao.curso_id.in_(curso_ids),
        )
    )
    pcts = [row[0] for row in inscricoes.all()]
    if not pcts:
        return None

    media = Decimal(str(round(sum(float(p) for p in pcts) / len(pcts), 2)))

    result = await db.execute(
        select(InscricaoTrilha).where(
            InscricaoTrilha.usuario_id == usuario_id,
            InscricaoTrilha.trilha_id == trilha_id,
        )
    )
    trilha_insc = result.scalar_one_or_none()
    if trilha_insc:
        trilha_insc.progresso_pct = media
        if media >= 100:
            trilha_insc.status = "concluido"
            if not trilha_insc.data_conclusao:
                trilha_insc.data_conclusao = datetime.now(timezone.utc)

    await db.flush()
    return trilha_insc


async def progresso_curso_detalhado(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    curso_id: int,
) -> dict:
    modulos = await db.execute(
        select(Modulo).where(Modulo.curso_id == curso_id).order_by(Modulo.ordem)
    )
    modulos_data = []
    for mod in modulos.scalars().all():
        unidades = await db.execute(
            select(Unidade).where(Unidade.modulo_id == mod.id).order_by(Unidade.ordem)
        )
        unids = unidades.scalars().all()
        total_u = len(unids)
        concluidas_u = 0

        for unid in unids:
            prog = await db.execute(
                select(ProgressoUnidade).where(
                    ProgressoUnidade.usuario_id == usuario_id,
                    ProgressoUnidade.unidade_id == unid.id,
                )
            )
            p = prog.scalar_one_or_none()
            if p and p.status == "concluido":
                concluidas_u += 1

        mod_pct = round((concluidas_u / total_u * 100), 2) if total_u else 0
        modulos_data.append({
            "id": mod.id,
            "titulo": mod.titulo,
            "total_unidades": total_u,
            "unidades_concluidas": concluidas_u,
            "progresso_pct": mod_pct,
        })

    return {
        "curso_id": curso_id,
        "modulos": modulos_data,
    }
