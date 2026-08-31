from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.sessao import Presenca, SessaoAoVivo
from app.models.usuario import Usuario
from app.services.paginacao import apply_search, count_query
from app.services.rbac import Permissoes
from app.schemas.sessao import (
    PresencaCreate,
    PresencaRead,
    PresencaUpdate,
    SessaoAoVivoCreate,
    SessaoAoVivoRead,
    SessaoAoVivoUpdate,
)

router = APIRouter(prefix="/sessoes", tags=["Sessoes ao Vivo"])


@router.get("", response_model=list[SessaoAoVivoRead])
async def listar_sessoes(
    curso_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, description="Busca textual por titulo"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_VISUALIZAR)),
):
    query = select(SessaoAoVivo)
    if curso_id is not None:
        query = query.where(SessaoAoVivo.curso_id == curso_id)
    query = apply_search(query, [SessaoAoVivo.titulo], q)
    total = await count_query(db, query)
    result = await db.execute(query.order_by(SessaoAoVivo.data_hora_inicio.desc()).offset(skip).limit(limit))
    items = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("", response_model=SessaoAoVivoRead, status_code=status.HTTP_201_CREATED)
async def criar_sessao(
    payload: SessaoAoVivoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_CRIAR)),
):
    sessao = SessaoAoVivo(**payload.model_dump())
    db.add(sessao)
    await db.commit()
    await db.refresh(sessao)
    return sessao


@router.get("/{sessao_id}", response_model=SessaoAoVivoRead)
async def obter_sessao(
    sessao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_VISUALIZAR)),
):
    result = await db.execute(select(SessaoAoVivo).where(SessaoAoVivo.id == sessao_id))
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    return sessao


@router.patch("/{sessao_id}", response_model=SessaoAoVivoRead)
async def atualizar_sessao(
    sessao_id: int,
    payload: SessaoAoVivoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_EDITAR)),
):
    result = await db.execute(select(SessaoAoVivo).where(SessaoAoVivo.id == sessao_id))
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sessao, field, value)
    await db.commit()
    await db.refresh(sessao)
    return sessao


@router.delete("/{sessao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_sessao(
    sessao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_EXCLUIR)),
):
    result = await db.execute(select(SessaoAoVivo).where(SessaoAoVivo.id == sessao_id))
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    await db.delete(sessao)
    await db.commit()


# --- Presenca ---


@router.post(
    "/presenca",
    response_model=PresencaRead,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def registrar_presenca(
    payload: PresencaCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_GERENCIAR_PRESENCA)),
):
    """LEGADO (issue 31): presenca oficial e a de aula (`PresencaAula`).

    Este sistema de presenca por sessao nao alimenta nenhum relatorio e nao
    e usado pelo front. Mantido apenas por compatibilidade.
    """
    sessao = await db.get(SessaoAoVivo, payload.sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    presenca = Presenca(**payload.model_dump())
    db.add(presenca)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Usuario nao encontrado")
    await db.refresh(presenca)
    return presenca


@router.get("/presenca/{sessao_id}", response_model=list[PresencaRead], deprecated=True)
async def listar_presenca(
    sessao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_VER_PRESENCA)),
):
    """LEGADO (issue 31): presenca oficial e a de aula (`PresencaAula`)."""
    result = await db.execute(select(Presenca).where(Presenca.sessao_id == sessao_id))
    return result.scalars().all()


@router.patch("/presenca/{presenca_id}", response_model=PresencaRead, deprecated=True)
async def atualizar_presenca(
    presenca_id: int,
    payload: PresencaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SESSAO_GERENCIAR_PRESENCA)),
):
    """LEGADO (issue 31): presenca oficial e a de aula (`PresencaAula`)."""
    result = await db.execute(select(Presenca).where(Presenca.id == presenca_id))
    presenca = result.scalar_one_or_none()
    if not presenca:
        raise HTTPException(status_code=404, detail="Registro de presenca nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(presenca, field, value)
    await db.commit()
    await db.refresh(presenca)
    return presenca
