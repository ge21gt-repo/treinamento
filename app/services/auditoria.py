"""Servico de auditoria (US-17, T-17.2).

Registra operacoes de escrita nas tabelas principais em `log_auditoria`,
com snapshot dos dados anteriores e novos, para rastreabilidade.
"""

import json
import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import LogAuditoria
from app.services.log_acesso import _detectar_dispositivo, _ip_cliente

CAMPOS_SENSIVEIS = ("senha_hash", "cpf", "telefone")


def sem_dados_sensiveis(dados: dict | None) -> dict | None:
    """Remove senha, CPF e telefone de um snapshot de usuario.

    `_serializar` copia TODA coluna da tabela, e `log_auditoria` tem trigger de
    imutabilidade (`prevent_log_auditoria_modify`): o que entra ali nao sai.
    As rotas de usuario ja faziam isso com `pop` repetido - aqui fica num ponto
    so, para uma rota nova nao esquecer. Foi o que aconteceu na #119.
    """
    if dados is None:
        return None
    return {k: v for k, v in dados.items() if k not in CAMPOS_SENSIVEIS}


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
    # Issue #120: alem do IP, guardar user_agent e dispositivo, para a aba de
    # Alteracoes mostrar as mesmas colunas da aba de Acessos. O IP passou a sair
    # de _ip_cliente, a mesma funcao que log_acesso usa: era logica duplicada,
    # e as duas abas tem de concordar sobre o IP da mesma requisicao.
    ip_address = None
    user_agent = None
    dispositivo = None
    if request:
        ip_address = _ip_cliente(request)
        user_agent = request.headers.get("user-agent") or None
        dispositivo = _detectar_dispositivo(user_agent or "")
    log = LogAuditoria(
        usuario_id=usuario_id,
        acao=acao,
        tabela_afetada=tabela,
        registro_id=str(registro_id),
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
        ip_address=ip_address,
        user_agent=user_agent,
        dispositivo=dispositivo,
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
