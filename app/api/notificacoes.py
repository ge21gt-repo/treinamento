"""Rotas de notificacoes (issue 28)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.notificacao import Notificacao
from app.models.usuario import Usuario
from app.schemas.notificacao import NotificacaoRead, NotificacoesListaRead

router = APIRouter(prefix="/notificacoes", tags=["Notificacoes"])


@router.get("", response_model=NotificacoesListaRead)
async def listar_notificacoes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Notificacoes do usuario logado, paginadas (issue 28)."""
    base = select(Notificacao).where(Notificacao.usuario_id == current_user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    nao_lidas = (
        await db.execute(
            select(func.count()).where(Notificacao.usuario_id == current_user.id, Notificacao.lida.is_(False))
        )
    ).scalar() or 0
    result = await db.execute(
        base.order_by(Notificacao.criado_em.desc()).offset(skip).limit(limit)
    )
    itens = result.scalars().all()
    return NotificacoesListaRead(
        itens=[NotificacaoRead.model_validate(n) for n in itens],
        total=total,
        nao_lidas=nao_lidas,
    )


@router.patch("/{notificacao_id}/lida", response_model=NotificacaoRead)
async def marcar_lida(
    notificacao_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Notificacao).where(
            Notificacao.id == notificacao_id,
            Notificacao.usuario_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificacao nao encontrada")
    notif.lida = True
    from datetime import datetime, timezone

    notif.lida_em = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notif)
    return notif


@router.post("/marcar-todas-lidas", status_code=status.HTTP_200_OK)
async def marcar_todas_lidas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Notificacao).where(
            Notificacao.usuario_id == current_user.id,
            Notificacao.lida.is_(False),
        )
    )
    for n in result.scalars().all():
        n.lida = True
        from datetime import datetime, timezone

        n.lida_em = datetime.now(timezone.utc)
    await db.commit()
    return {"atualizadas": True}