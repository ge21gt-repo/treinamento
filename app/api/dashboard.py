import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.avaliacao import ResultadoAvaliacao
from app.models.certificado import Certificado
from app.models.curso import Curso, Inscricao, TrilhaAprendizagem
from app.models.gamificacao import PontosXP
from app.models.log import LogAcesso, MetricaEngajamento
from app.models.sessao import SessaoAoVivo
from app.models.usuario import Usuario
from app.schemas.log import LogAcessoRead, MetricaEngajamentoRead

router = APIRouter(prefix="/dashboard", tags=["Dashboard e Analytics"])


@router.get("/resumo")
async def resumo_geral(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    total_usuarios = (await db.execute(select(func.count(Usuario.id)))).scalar()
    total_cursos = (await db.execute(select(func.count(Curso.id)))).scalar()
    total_trilhas = (await db.execute(select(func.count(TrilhaAprendizagem.id)))).scalar()
    total_inscricoes = (await db.execute(select(func.count(Inscricao.id)))).scalar()
    total_certificados = (await db.execute(select(func.count(Certificado.id)))).scalar()
    total_sessoes = (await db.execute(select(func.count(SessaoAoVivo.id)))).scalar()
    return {
        "total_usuarios": total_usuarios,
        "total_cursos": total_cursos,
        "total_trilhas": total_trilhas,
        "total_inscricoes": total_inscricoes,
        "total_certificados": total_certificados,
        "total_sessoes_ao_vivo": total_sessoes,
    }


@router.get("/metricas/{usuario_id}", response_model=list[MetricaEngajamentoRead])
async def metricas_usuario(
    usuario_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(MetricaEngajamento)
        .where(MetricaEngajamento.usuario_id == usuario_id)
        .order_by(MetricaEngajamento.data_referencia.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/logs", response_model=list[LogAcessoRead])
async def listar_logs(
    usuario_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(LogAcesso)
    if usuario_id is not None:
        q = q.where(LogAcesso.usuario_id == usuario_id)
    result = await db.execute(q.order_by(LogAcesso.criado_em.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/cursos/{curso_id}/stats")
async def stats_curso(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    total_inscritos = (
        await db.execute(select(func.count(Inscricao.id)).where(Inscricao.curso_id == curso_id))
    ).scalar()
    concluidos = (
        await db.execute(
            select(func.count(Inscricao.id)).where(
                Inscricao.curso_id == curso_id, Inscricao.status == "concluido"
            )
        )
    ).scalar()
    nota_media = (
        await db.execute(
            select(func.avg(Inscricao.nota_final)).where(
                Inscricao.curso_id == curso_id, Inscricao.nota_final.isnot(None)
            )
        )
    ).scalar()
    return {
        "curso_id": curso_id,
        "total_inscritos": total_inscritos,
        "total_concluidos": concluidos,
        "nota_media": float(nota_media) if nota_media else None,
        "taxa_conclusao": round((concluidos / total_inscritos * 100), 2) if total_inscritos else 0,
    }
