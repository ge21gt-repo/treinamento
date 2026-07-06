import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.curso import Curso, Inscricao, Modulo, ProgressoUnidade, Unidade
from app.models.usuario import Usuario
from app.schemas.curso import (
    CursoCreate,
    CursoRead,
    CursoUpdate,
    InscricaoCreate,
    InscricaoRead,
    ModuloCreate,
    ModuloRead,
    ModuloUpdate,
    ProgressoUnidadeCreate,
    ProgressoUnidadeRead,
    ProgressoUnidadeUpdate,
    UnidadeCreate,
    UnidadeRead,
    UnidadeUpdate,
)

router = APIRouter(prefix="/cursos", tags=["Cursos"])


# --- Cursos ---

@router.get("", response_model=list[CursoRead])
async def listar_cursos(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    trilha_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    stmt = select(Curso)
    if trilha_id is not None:
        stmt = stmt.where(Curso.trilha_id == trilha_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=CursoRead, status_code=status.HTTP_201_CREATED)
async def criar_curso(
    payload: CursoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    curso = Curso(**payload.model_dump())
    db.add(curso)
    await db.commit()
    await db.refresh(curso)
    return curso


@router.get("/{curso_id}", response_model=CursoRead)
async def obter_curso(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Curso).where(Curso.id == curso_id))
    curso = result.scalar_one_or_none()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
    return curso


@router.patch("/{curso_id}", response_model=CursoRead)
async def atualizar_curso(
    curso_id: int,
    payload: CursoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Curso).where(Curso.id == curso_id))
    curso = result.scalar_one_or_none()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(curso, field, value)
    await db.commit()
    await db.refresh(curso)
    return curso


@router.delete("/{curso_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_curso(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Curso).where(Curso.id == curso_id))
    curso = result.scalar_one_or_none()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
    await db.delete(curso)
    await db.commit()


# --- Modulos ---

@router.get("/{curso_id}/modulos", response_model=list[ModuloRead])
async def listar_modulos(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Modulo).where(Modulo.curso_id == curso_id).order_by(Modulo.ordem))
    return result.scalars().all()


@router.post("/modulos", response_model=ModuloRead, status_code=status.HTTP_201_CREATED)
async def criar_modulo(
    payload: ModuloCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    modulo = Modulo(**payload.model_dump())
    db.add(modulo)
    await db.commit()
    await db.refresh(modulo)
    return modulo


@router.patch("/modulos/{modulo_id}", response_model=ModuloRead)
async def atualizar_modulo(
    modulo_id: int,
    payload: ModuloUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Modulo).where(Modulo.id == modulo_id))
    modulo = result.scalar_one_or_none()
    if not modulo:
        raise HTTPException(status_code=404, detail="Modulo nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(modulo, field, value)
    await db.commit()
    await db.refresh(modulo)
    return modulo


@router.delete("/modulos/{modulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_modulo(
    modulo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Modulo).where(Modulo.id == modulo_id))
    modulo = result.scalar_one_or_none()
    if not modulo:
        raise HTTPException(status_code=404, detail="Modulo nao encontrado")
    await db.delete(modulo)
    await db.commit()


# --- Unidades ---

@router.get("/modulos/{modulo_id}/unidades", response_model=list[UnidadeRead])
async def listar_unidades(
    modulo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Unidade).where(Unidade.modulo_id == modulo_id).order_by(Unidade.ordem))
    return result.scalars().all()


@router.post("/unidades", response_model=UnidadeRead, status_code=status.HTTP_201_CREATED)
async def criar_unidade(
    payload: UnidadeCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    unidade = Unidade(**payload.model_dump())
    db.add(unidade)
    await db.commit()
    await db.refresh(unidade)
    return unidade


@router.patch("/unidades/{unidade_id}", response_model=UnidadeRead)
async def atualizar_unidade(
    unidade_id: int,
    payload: UnidadeUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Unidade).where(Unidade.id == unidade_id))
    unidade = result.scalar_one_or_none()
    if not unidade:
        raise HTTPException(status_code=404, detail="Unidade nao encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(unidade, field, value)
    await db.commit()
    await db.refresh(unidade)
    return unidade


@router.delete("/unidades/{unidade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_unidade(
    unidade_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Unidade).where(Unidade.id == unidade_id))
    unidade = result.scalar_one_or_none()
    if not unidade:
        raise HTTPException(status_code=404, detail="Unidade nao encontrada")
    await db.delete(unidade)
    await db.commit()


# --- Inscricoes ---

@router.post("/inscricoes", response_model=InscricaoRead, status_code=status.HTTP_201_CREATED)
async def inscrever(
    payload: InscricaoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    inscricao = Inscricao(**payload.model_dump())
    db.add(inscricao)
    await db.commit()
    await db.refresh(inscricao)
    return inscricao


@router.get("/inscricoes/{usuario_id}", response_model=list[InscricaoRead])
async def listar_inscricoes_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Inscricao).where(Inscricao.usuario_id == usuario_id))
    return result.scalars().all()


# --- Progresso ---

@router.post("/progresso", response_model=ProgressoUnidadeRead, status_code=status.HTTP_201_CREATED)
async def criar_progresso(
    payload: ProgressoUnidadeCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    progresso = ProgressoUnidade(**payload.model_dump())
    db.add(progresso)
    await db.commit()
    await db.refresh(progresso)
    return progresso


@router.patch("/progresso/{progresso_id}", response_model=ProgressoUnidadeRead)
async def atualizar_progresso(
    progresso_id: int,
    payload: ProgressoUnidadeUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(ProgressoUnidade).where(ProgressoUnidade.id == progresso_id))
    progresso = result.scalar_one_or_none()
    if not progresso:
        raise HTTPException(status_code=404, detail="Progresso nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(progresso, field, value)
    await db.commit()
    await db.refresh(progresso)
    return progresso
