"""Servico de notificacoes (issue 28)."""

import uuid

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curso import Inscricao
from app.models.notificacao import Notificacao
from app.models.usuario import Usuario
from app.services.email import send_notificacao_email

# Nem todo aviso merece e-mail -- so os que fazem a pessoa ir a algum lugar
# num horario especifico (issue 42).
TIPOS_QUE_VAO_POR_EMAIL = {"aula_agendada", "gravacao_disponivel"}


async def notificar_inscritos(
    db: AsyncSession,
    curso_id: int,
    tipo: str,
    titulo: str,
    corpo: str | None = None,
    referencia_tipo: str | None = None,
    referencia_id: int | None = None,
    background_tasks: BackgroundTasks | None = None,
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

    # O envio nao pode atrasar a resposta (SMTP lento/fora do ar nao pode travar
    # o agendamento de aula) -- BackgroundTasks roda depois da resposta ser
    # enviada (issue 42). Sem background_tasks (ex.: chamador sem request), so
    # pula o e-mail em vez de bloquear.
    if background_tasks is not None and tipo in TIPOS_QUE_VAO_POR_EMAIL and usuarios:
        emails = await db.execute(select(Usuario.email).where(Usuario.id.in_(usuarios)))
        for (email,) in emails.all():
            background_tasks.add_task(send_notificacao_email, email, titulo, corpo)

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
