"""Servico de log de acesso (US-17, T-17.1).

Registra operacoes de escrita (POST/PATCH/DELETE) e eventos relevantes
em `log_acesso`, para rastreabilidade de quem fez o quê.
"""

import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import LogAcesso


def _detectar_dispositivo(user_agent: str) -> str | None:
    """Identifica o tipo de dispositivo a partir do user-agent (T-17.1)."""
    ua = (user_agent or "").lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua or "ipad" in ua:
        return "mobile"
    if "tablet" in ua or "ipad" in ua:
        return "tablet"
    if not ua:
        return None
    return "desktop"


def _ip_cliente(request: Request) -> str | None:
    """Extrai o IP real do cliente (X-Forwarded-For) com fallback em client.host."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.client.host if request.client else None


async def registrar_log_acesso(
    db: AsyncSession,
    request: Request,
    usuario_id: uuid.UUID,
    acao: str,
    recurso_tipo: str | None = None,
    recurso_id: int | None = None,
) -> LogAcesso:
    """Registra um acesso/operacao no log_acesso (T-17.1)."""
    user_agent = request.headers.get("user-agent", "")
    log = LogAcesso(
        usuario_id=usuario_id,
        acao=acao,
        recurso_tipo=recurso_tipo,
        recurso_id=recurso_id,
        ip_address=_ip_cliente(request),
        user_agent=user_agent[:1000] or None,
        dispositivo=_detectar_dispositivo(user_agent),
    )
    db.add(log)
    return log