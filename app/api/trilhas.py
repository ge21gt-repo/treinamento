from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.curso import TrilhaAprendizagem
from app.models.usuario import Usuario
from app.schemas.curso import TrilhaCreate, TrilhaRead, TrilhaUpdate

router = APIRouter(prefix="/trilhas", tags=["Trilhas de Aprendizagem"])


@router.get("", response_model=list[TrilhaRead])
async def listar_trilhas(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(TrilhaAprendizagem).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=TrilhaRead, status_code=status.HTTP_201_CREATED)
async def criar_trilha(
    payload: TrilhaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    trilha = TrilhaAprendizagem(**payload.model_dump(), criado_por=current_user.id)
    db.add(trilha)
    await db.commit()
    await db.refresh(trilha)
    return trilha


@router.get("/{trilha_id}", response_model=TrilhaRead)
async def obter_trilha(
    trilha_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(TrilhaAprendizagem).where(TrilhaAprendizagem.id == trilha_id))
    trilha = result.scalar_one_or_none()
    if not trilha:
        raise HTTPException(status_code=404, detail="Trilha nao encontrada")
    return trilha


@router.patch("/{trilha_id}", response_model=TrilhaRead)
async def atualizar_trilha(
    trilha_id: int,
    payload: TrilhaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(TrilhaAprendizagem).where(TrilhaAprendizagem.id == trilha_id))
    trilha = result.scalar_one_or_none()
    if not trilha:
        raise HTTPException(status_code=404, detail="Trilha nao encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(trilha, field, value)
    await db.commit()
    await db.refresh(trilha)
    return trilha


@router.delete("/{trilha_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_trilha(
    trilha_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(TrilhaAprendizagem).where(TrilhaAprendizagem.id == trilha_id))
    trilha = result.scalar_one_or_none()
    if not trilha:
        raise HTTPException(status_code=404, detail="Trilha nao encontrada")
    await db.delete(trilha)
    await db.commit()
