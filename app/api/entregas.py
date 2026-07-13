import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.conteudo import EntregaAtividade
from app.models.usuario import Usuario
from app.schemas.conteudo import EntregaAtividadeCorrigir, EntregaAtividadeRead
from app.services.rbac import Permissoes
from app.services.storage import upload_file

router = APIRouter(prefix="/entregas", tags=["Entregas"])


@router.post("/upload", response_model=EntregaAtividadeRead, status_code=status.HTTP_201_CREATED)
async def criar_entrega(
    unidade_id: int = Query(...),
    titulo: str = Query(...),
    descricao: str | None = Query(None),
    arquivo: UploadFile = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.ENTREGA_CRIAR)),
):
    url = await upload_file(arquivo, "exercicios")
    entrega = EntregaAtividade(
        unidade_id=unidade_id,
        usuario_id=current_user.id,
        titulo=titulo,
        descricao=descricao,
        mime_type=arquivo.content_type,
        url_arquivo=url,
    )
    db.add(entrega)
    await db.commit()
    await db.refresh(entrega)
    return entrega


@router.get("/unidade/{unidade_id}", response_model=list[EntregaAtividadeRead])
async def listar_entregas_unidade(
    unidade_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.ENTREGA_VISUALIZAR)),
):
    result = await db.execute(
        select(EntregaAtividade)
        .where(EntregaAtividade.unidade_id == unidade_id)
        .order_by(EntregaAtividade.criado_em.desc())
    )
    return result.scalars().all()


@router.get("/minhas", response_model=list[EntregaAtividadeRead])
async def listar_minhas_entregas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.ENTREGA_VISUALIZAR)),
):
    result = await db.execute(
        select(EntregaAtividade)
        .where(EntregaAtividade.usuario_id == current_user.id)
        .order_by(EntregaAtividade.criado_em.desc())
    )
    return result.scalars().all()


@router.get("/usuario/{usuario_id}", response_model=list[EntregaAtividadeRead])
async def listar_entregas_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.ENTREGA_VISUALIZAR)),
):
    result = await db.execute(
        select(EntregaAtividade)
        .where(EntregaAtividade.usuario_id == usuario_id)
        .order_by(EntregaAtividade.criado_em.desc())
    )
    return result.scalars().all()


@router.get("/{entrega_id}", response_model=EntregaAtividadeRead)
async def obter_entrega(
    entrega_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.ENTREGA_VISUALIZAR)),
):
    result = await db.execute(select(EntregaAtividade).where(EntregaAtividade.id == entrega_id))
    entrega = result.scalar_one_or_none()
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega nao encontrada")
    return entrega


@router.patch("/{entrega_id}/corrigir", response_model=EntregaAtividadeRead)
async def corrigir_entrega(
    entrega_id: int,
    payload: EntregaAtividadeCorrigir,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.ENTREGA_CORRIGIR)),
):
    result = await db.execute(select(EntregaAtividade).where(EntregaAtividade.id == entrega_id))
    entrega = result.scalar_one_or_none()
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega nao encontrada")
    entrega.nota = payload.nota
    entrega.feedback = payload.feedback
    entrega.status = "corrigido"
    await db.commit()
    await db.refresh(entrega)
    return entrega
