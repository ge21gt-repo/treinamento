"""Servico de notificacoes (issue 28)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curso import Inscricao
from app.models.notificacao import Notificacao


async def notificar_inscritos(
    db: AsyncSession,
    curso_id: int,
    tipo: str,
    titulo: str,
    corpo: str | None = None,
    referencia_tipo: str | None = None,
    referencia_id: int | None = None,
) -> int:
    """Cria uma notificacao para todos os inscritos de um curso (issue 28)."""
    inscritos = await db.execute(
        select(Inscricao.usuario_id).where(Inscricao.curso_id == curso_id)
    )
    usuarios = {row[0] for row in inscritos.all()}
    for uid in usuarios:
        db.add(
            Notificacao(
                usuario_id=uid,
                tipo=tipo,
                titulo=titulo,
                corpo=corpo,
                referencia_tipo=referencia_tipo,
                referencia_id=referencia_id,
            )
        )
    await db.flush()
    return len(usuarios)


async def notificar_usuario(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    tipo: str,
    titulo: str,
    corpo: str | None = None,
    referencia_tipo: str | None = None,
    referencia_id: int | None = None,
) -> Notificacao:
    notif = Notificacao(
        usuario_id=usuario_id,
        tipo=tipo,
        titulo=titulo,
        corpo=corpo,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
    )
    db.add(notif)
    await db.flush()
    return notif