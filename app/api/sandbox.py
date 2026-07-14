from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.sandbox import SandboxEncerrarResponse, SandboxIniciarRequest, SandboxSessaoRead
from app.services import sandbox as sandbox_service
from app.services.rbac import Permissoes

router = APIRouter(prefix="/sandbox", tags=["Sandbox"])


@router.post("/iniciar", response_model=SandboxSessaoRead, status_code=status.HTTP_201_CREATED)
async def iniciar_sandbox(
    payload: SandboxIniciarRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.SANDBOX_TESTAR)),
):
    sessao = await sandbox_service.iniciar_sessao(
        db=db,
        usuario_id=current_user.id,
        observacao=payload.observacao,
    )
    return sessao


@router.post("/{sessao_id}/encerrar", response_model=SandboxEncerrarResponse)
async def encerrar_sandbox(
    sessao_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.SANDBOX_TESTAR)),
):
    try:
        sessao = await sandbox_service.encerrar_sessao(
            db=db,
            sessao_id=sessao_id,
            usuario_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    duracao = None
    if sessao.iniciado_em and sessao.encerrado_em:
        duracao = int((sessao.encerrado_em - sessao.iniciado_em).total_seconds())

    return SandboxEncerrarResponse(
        message="Sessao sandbox encerrada com sucesso",
        sessao_id=sessao.id,
        usuario_id=sessao.usuario_id,
        duracao_segundos=duracao,
    )


@router.get("/ativo", response_model=SandboxSessaoRead | None)
async def verificar_sandbox_ativo(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    sessoes = await sandbox_service.listar_sessoes(db=db, usuario_id=current_user.id, apenas_ativas=True)
    return sessoes[0] if sessoes else None


@router.get("/sessoes", response_model=list[SandboxSessaoRead])
async def listar_sessoes_sandbox(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return await sandbox_service.listar_sessoes(db=db, usuario_id=current_user.id)
