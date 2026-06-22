import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.schemas.usuario import PerfilCreate, PerfilRead, UsuarioPerfilCreate, UsuarioRead, UsuarioUpdate

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/me", response_model=UsuarioRead)
async def me(current_user: Usuario = Depends(get_current_user)):
    return current_user


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Usuario).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{usuario_id}", response_model=UsuarioRead)
async def obter_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    return user


@router.patch("/{usuario_id}", response_model=UsuarioRead)
async def atualizar_usuario(
    usuario_id: uuid.UUID,
    payload: UsuarioUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    await db.delete(user)
    await db.commit()


# --- Perfis ---

@router.get("/perfis/todos", response_model=list[PerfilRead])
async def listar_perfis(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Perfil))
    return result.scalars().all()


@router.post("/perfis", response_model=PerfilRead, status_code=status.HTTP_201_CREATED)
async def criar_perfil(
    payload: PerfilCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    perfil = Perfil(**payload.model_dump())
    db.add(perfil)
    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.post("/perfis/atribuir", status_code=status.HTTP_201_CREATED)
async def atribuir_perfil(
    payload: UsuarioPerfilCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    up = UsuarioPerfil(
        usuario_id=payload.usuario_id,
        perfil_id=payload.perfil_id,
        atribuido_por=current_user.id,
    )
    db.add(up)
    await db.commit()
    return {"detail": "Perfil atribuido com sucesso"}
