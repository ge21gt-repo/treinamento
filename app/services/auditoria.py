"""Servico de auditoria (US-17, T-17.2).

Registra operacoes de escrita nas tabelas principais em `log_auditoria`,
com snapshot dos dados anteriores e novos, para rastreabilidade.
"""

import json
import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import LogAuditoria


def _serializar(obj) -> dict | None:
    """Serializa um objeto SQLAlchemy para dict (para snapshot)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    data = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name, None)
        if val is None:
            data[col.name] = None
        elif isinstance(val, (uuid.UUID,)):
            data[col.name] = str(val)
        elif hasattr(val, "isoformat"):
            data[col.name] = val.isoformat()
        else:
            try:
                json.dumps(val)
                data[col.name] = val
            except (TypeError, ValueError):
                data[col.name] = str(val)
    return data


async def registrar_auditoria(
    db: AsyncSession,
    tabela: str,
    registro_id: str,
    acao: str,
    dados_anteriores: dict | None = None,
    dados_novos: dict | None = None,
    usuario_id: uuid.UUID | None = None,
    request: Request | None = None,
) -> LogAuditoria:
    """Grava um registro de auditoria em log_auditoria (T-17.2)."""
    ip_address = None
    if request:
        xff = request.headers.get("x-forwarded-for", "")
        ip_address = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
    log = LogAuditoria(
        usuario_id=usuario_id,
        acao=acao,
        tabela_afetada=tabela,
        registro_id=str(registro_id),
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
        ip_address=ip_address,
    )
    db.add(log)
    return log

async def auditar_escrita(
    db: AsyncSession,
    tabela: str,
    registro_id,
    acao: str,
    dados_anteriores: dict | None = None,
    dados_novos: dict | None = None,
    usuario_id: uuid.UUID | None = None,
    request: Request | None = None,
) -> LogAuditoria:
    """Atalho para registrar auditoria e commit (T-17.2)."""
    log = await registrar_auditoria(
        db, tabela, registro_id, acao, dados_anteriores, dados_novos, usuario_id, request
    )
    await db.commit()
    return log
