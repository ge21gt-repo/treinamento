"""Rotas de consulta de logs de auditoria (US-17, T-17.3/17.4/17.5)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissao
from app.database import get_db
from app.models.log import LogAuditoria
from app.models.usuario import Usuario
from app.schemas.log import LogAuditoriaRead
from app.services.paginacao import count_query
from app.services.rbac import Permissoes

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


@router.get("/logs", response_model=list[LogAuditoriaRead])
async def listar_logs_auditoria(
    tabela: str | None = Query(None, description="Filtra por tabela_afetada"),
    usuario_id: uuid.UUID | None = Query(None, description="Filtra por usuario"),
    acao: str | None = Query(None, description="Filtra por acao (criar/atualizar/excluir)"),
    data_inicio: datetime | None = Query(None, description="Inicio do periodo (ISO)"),
    data_fim: datetime | None = Query(None, description="Fim do periodo (ISO)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    formato: str = Query("json", pattern="^(json|csv|pdf)$"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.AUDITORIA_VISUALIZAR)),
):
    """Consulta logs de auditoria com filtros e exportacao (T-17.3/17.4/17.5)."""
    query = select(LogAuditoria)
    if tabela is not None:
        query = query.where(LogAuditoria.tabela_afetada == tabela)
    if usuario_id is not None:
        query = query.where(LogAuditoria.usuario_id == usuario_id)
    if acao is not None:
        query = query.where(LogAuditoria.acao == acao)
    if data_inicio is not None:
        query = query.where(LogAuditoria.criado_em >= data_inicio)
    if data_fim is not None:
        query = query.where(LogAuditoria.criado_em <= data_fim)

    total = await count_query(db, query)
    result = await db.execute(query.order_by(LogAuditoria.criado_em.desc()).offset(skip).limit(limit))
    logs = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)

    if formato == "csv":
        return _logs_csv(logs)
    if formato == "pdf":
        return _logs_pdf(logs)
    return [LogAuditoriaRead.model_validate(l) for l in logs]


def _logs_csv(logs: list[LogAuditoria]) -> StreamingResponse:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["id", "usuario_id", "acao", "tabela_afetada", "registro_id", "criado_em"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for l in logs:
        writer.writerow(
            {
                "id": l.id,
                "usuario_id": str(l.usuario_id) if l.usuario_id else "",
                "acao": l.acao,
                "tabela_afetada": l.tabela_afetada,
                "registro_id": l.registro_id,
                "criado_em": l.criado_em.isoformat(),
            }
        )
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv")


def _logs_pdf(logs: list[LogAuditoria]) -> StreamingResponse:
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    estilos = getSampleStyleSheet()
    cabecalho = ["id", "acao", "tabela", "registro", "usuario", "criado_em"]
    dados = [cabecalho] + [
        [
            l.id,
            l.acao,
            l.tabela_afetada,
            l.registro_id,
            str(l.usuario_id)[:8] if l.usuario_id else "",
            l.criado_em.strftime("%d/%m/%Y %H:%M"),
        ]
        for l in logs
    ]
    tabela = Table(dados)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    doc.build([Paragraph("Logs de Auditoria", estilos["Title"]), tabela])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/pdf")