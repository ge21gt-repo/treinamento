from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_permissao
from app.services.rbac import Permissoes
from app.database import get_db
from app.models.credenciamento import SolicitacaoCredenciamento
from app.models.usuario import Usuario
from app.schemas.credenciamento import AprovacaoSolicitacaoRequest, SolicitacaoCredenciamentoRead
from app.services.credenciamento import aprovar_solicitacao, rejeitar_solicitacao

router = APIRouter(prefix="/credenciamento", tags=["Credenciamento"])


@router.get("/solicitacoes/pendentes", response_model=list[SolicitacaoCredenciamentoRead])
async def listar_solicitacoes_pendentes(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permissao(Permissoes.CREDENCIAMENTO_LISTAR)),
):
    """Listar todas as solicitacoes de credenciamento pendentes"""
    # TODO: No futuro, filtrar por hierarquia do usuario atual
    # Por enquanto, retorna todas as pendentes
    result = await db.execute(
        select(SolicitacaoCredenciamento)
        .options(selectinload(SolicitacaoCredenciamento.usuario))
        .where(SolicitacaoCredenciamento.status == "pendente")
        .order_by(SolicitacaoCredenciamento.solicitado_em)
    )
    solicitacoes = result.scalars().all()
    return solicitacoes


@router.post("/solicitacoes/{solicitacao_id}/aprovar")
async def aprovar_solicitacao_endpoint(
    solicitacao_id: int,
    payload: AprovacaoSolicitacaoRequest,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permissao(Permissoes.CREDENCIAMENTO_APROVAR)),
):
    """Aprovar uma solicitacao de credenciamento"""
    try:
        resultado = await aprovar_solicitacao(
            solicitacao_id=solicitacao_id, aprovador_id=current_user.id, observacao=payload.observacao, db=db
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/solicitacoes/{solicitacao_id}/rejeitar")
async def rejeitar_solicitacao_endpoint(
    solicitacao_id: int,
    payload: AprovacaoSolicitacaoRequest,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permissao(Permissoes.CREDENCIAMENTO_APROVAR)),
):
    """Rejeitar uma solicitacao de credenciamento"""
    if not payload.observacao:
        raise HTTPException(status_code=400, detail="Motivo obrigatorio para rejeicao")

    try:
        resultado = await rejeitar_solicitacao(
            solicitacao_id=solicitacao_id, aprovador_id=current_user.id, motivo=payload.observacao, db=db
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
