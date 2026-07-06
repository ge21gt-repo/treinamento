import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sandbox import SandboxSessao


async def iniciar_sessao(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    observacao: str | None = None,
) -> SandboxSessao:
    sessao = SandboxSessao(
        usuario_id=usuario_id,
        status="ativo",
        observacao=observacao,
    )
    db.add(sessao)
    await db.commit()
    await db.refresh(sessao)
    return sessao


async def encerrar_sessao(
    db: AsyncSession,
    sessao_id: int,
    usuario_id: uuid.UUID,
) -> SandboxSessao:
    result = await db.execute(
        select(SandboxSessao).where(
            SandboxSessao.id == sessao_id,
            SandboxSessao.usuario_id == usuario_id,
        )
    )
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise ValueError("Sessao sandbox nao encontrada")
    if sessao.status != "ativo":
        raise ValueError("Sessao sandbox ja foi encerrada")

    sessao.status = "encerrado"
    sessao.encerrado_em = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sessao)
    return sessao


async def listar_sessoes(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    apenas_ativas: bool = False,
) -> list[SandboxSessao]:
    query = select(SandboxSessao).where(SandboxSessao.usuario_id == usuario_id)
    if apenas_ativas:
        query = query.where(SandboxSessao.status == "ativo")
    query = query.order_by(SandboxSessao.iniciado_em.desc())
    result = await db.execute(query)
    return result.scalars().all()


async def sessao_ativa_exists(
    db: AsyncSession,
    usuario_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(SandboxSessao).where(
            SandboxSessao.usuario_id == usuario_id,
            SandboxSessao.status == "ativo",
        )
    )
    return result.scalar_one_or_none() is not None
