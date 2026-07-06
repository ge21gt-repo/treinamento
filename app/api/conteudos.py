from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.conteudo import Conteudo, MaterialComplementar
from app.models.usuario import Usuario
from app.schemas.conteudo import (
    ConteudoCreate,
    ConteudoRead,
    ConteudoUpdate,
    MaterialComplementarCreate,
    MaterialComplementarRead,
)

router = APIRouter(prefix="/conteudos", tags=["Conteudos"])


@router.get("", response_model=list[ConteudoRead])
async def listar_conteudos(
    unidade_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = select(Conteudo)
    if unidade_id is not None:
        q = q.where(Conteudo.unidade_id == unidade_id)
    q = q.order_by(Conteudo.ordem).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=ConteudoRead, status_code=status.HTTP_201_CREATED)
async def criar_conteudo(
    payload: ConteudoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    conteudo = Conteudo(**payload.model_dump(), criado_por=current_user.id)
    db.add(conteudo)
    await db.commit()
    await db.refresh(conteudo)
    return conteudo


@router.get("/{conteudo_id}", response_model=ConteudoRead)
async def obter_conteudo(
    conteudo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    return conteudo


@router.patch("/{conteudo_id}", response_model=ConteudoRead)
async def atualizar_conteudo(
    conteudo_id: int,
    payload: ConteudoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(conteudo, field, value)
    await db.commit()
    await db.refresh(conteudo)
    return conteudo


@router.delete("/{conteudo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_conteudo(
    conteudo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    await db.delete(conteudo)
    await db.commit()


# --- Materiais Complementares ---

@router.get("/materiais/{curso_id}", response_model=list[MaterialComplementarRead])
async def listar_materiais(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(MaterialComplementar).where(MaterialComplementar.curso_id == curso_id))
    return result.scalars().all()


@router.post("/materiais", response_model=MaterialComplementarRead, status_code=status.HTTP_201_CREATED)
async def criar_material(
    payload: MaterialComplementarCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    material = MaterialComplementar(**payload.model_dump(), criado_por=current_user.id)
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material
