from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.curso import Curso, Inscricao, InscricaoTrilha, TrilhaAprendizagem
from app.models.usuario import Usuario
from app.schemas.curso import InscricaoTrilhaRead, TrilhaCreate, TrilhaProgressoRead, TrilhaRead, TrilhaUpdate
from app.services.rbac import Permissoes

router = APIRouter(prefix="/trilhas", tags=["Trilhas de Aprendizagem"])


@router.get("", response_model=list[TrilhaRead])
async def listar_trilhas(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    nivel: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    stmt = select(TrilhaAprendizagem)
    if nivel:
        stmt = stmt.where(TrilhaAprendizagem.nivel == nivel)
    result = await db.execute(stmt.offset(skip).limit(limit))
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


@router.get("/minhas-trilhas", response_model=list[TrilhaProgressoRead])
async def listar_minhas_trilhas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(InscricaoTrilha)
        .where(InscricaoTrilha.usuario_id == current_user.id)
        .options(selectinload(InscricaoTrilha.trilha).selectinload(TrilhaAprendizagem.cursos))
    )
    inscricoes = result.scalars().all()

    resultado = []
    for inscricao in inscricoes:
        trilha = inscricao.trilha
        cursos_ids = [c.id for c in trilha.cursos]
        total_cursos = len(cursos_ids)

        if total_cursos == 0:
            resultado.append(TrilhaProgressoRead(
                trilha_id=trilha.id,
                titulo=trilha.titulo,
                nivel=trilha.nivel,
                carga_horaria_total=trilha.carga_horaria_total,
                total_cursos=0,
                cursos_concluidos=0,
                progresso_pct=inscricao.progresso_pct,
                status=inscricao.status,
                data_inscricao=inscricao.data_inscricao,
                data_conclusao=inscricao.data_conclusao,
            ))
            continue

        result_insc = await db.execute(
            select(
                func.count(Inscricao.id).filter(Inscricao.status == "concluido").label("concluidos"),
                func.coalesce(func.avg(Inscricao.progresso_pct), 0).label("media"),
            ).where(
                Inscricao.usuario_id == current_user.id,
                Inscricao.curso_id.in_(cursos_ids),
            )
        )
        row = result_insc.one()

        resultado.append(TrilhaProgressoRead(
            trilha_id=trilha.id,
            titulo=trilha.titulo,
            nivel=trilha.nivel,
            carga_horaria_total=trilha.carga_horaria_total,
            total_cursos=total_cursos,
            cursos_concluidos=row.concluidos,
            progresso_pct=round(row.media, 2),
            status=inscricao.status,
            data_inscricao=inscricao.data_inscricao,
            data_conclusao=inscricao.data_conclusao,
        ))

    return resultado


@router.get("/{trilha_id}/progresso", response_model=TrilhaProgressoRead)
async def ver_progresso_trilha(
    trilha_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    _: Usuario = Depends(require_permissao(Permissoes.TRILHA_VER_PROGRESSO)),
):
    result = await db.execute(
        select(InscricaoTrilha)
        .where(
            InscricaoTrilha.usuario_id == current_user.id,
            InscricaoTrilha.trilha_id == trilha_id,
        )
        .options(selectinload(InscricaoTrilha.trilha).selectinload(TrilhaAprendizagem.cursos))
    )
    inscricao = result.scalar_one_or_none()
    if not inscricao:
        raise HTTPException(status_code=404, detail="Inscricao nao encontrada nesta trilha")

    trilha = inscricao.trilha
    cursos_ids = [c.id for c in trilha.cursos]
    total_cursos = len(cursos_ids)

    if total_cursos == 0:
        return TrilhaProgressoRead(
            trilha_id=trilha.id,
            titulo=trilha.titulo,
            nivel=trilha.nivel,
            carga_horaria_total=trilha.carga_horaria_total,
            total_cursos=0,
            cursos_concluidos=0,
            progresso_pct=inscricao.progresso_pct,
            status=inscricao.status,
            data_inscricao=inscricao.data_inscricao,
            data_conclusao=inscricao.data_conclusao,
        )

    result_insc = await db.execute(
        select(
            func.count(Inscricao.id).filter(Inscricao.status == "concluido").label("concluidos"),
            func.coalesce(func.avg(Inscricao.progresso_pct), 0).label("media"),
        ).where(
            Inscricao.usuario_id == current_user.id,
            Inscricao.curso_id.in_(cursos_ids),
        )
    )
    row = result_insc.one()

    return TrilhaProgressoRead(
        trilha_id=trilha.id,
        titulo=trilha.titulo,
        nivel=trilha.nivel,
        carga_horaria_total=trilha.carga_horaria_total,
        total_cursos=total_cursos,
        cursos_concluidos=row.concluidos,
        progresso_pct=round(row.media, 2),
        status=inscricao.status,
        data_inscricao=inscricao.data_inscricao,
        data_conclusao=inscricao.data_conclusao,
    )


@router.post("/{trilha_id}/inscrever", response_model=InscricaoTrilhaRead, status_code=status.HTTP_201_CREATED)
async def inscrever_trilha(
    trilha_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    _: Usuario = Depends(require_permissao(Permissoes.TRILHA_INSCREVER)),
):
    result = await db.execute(select(TrilhaAprendizagem).where(TrilhaAprendizagem.id == trilha_id))
    trilha = result.scalar_one_or_none()
    if not trilha:
        raise HTTPException(status_code=404, detail="Trilha nao encontrada")

    result = await db.execute(
        select(InscricaoTrilha).where(
            InscricaoTrilha.usuario_id == current_user.id,
            InscricaoTrilha.trilha_id == trilha_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Usuario ja inscrito nesta trilha")

    inscricao = InscricaoTrilha(usuario_id=current_user.id, trilha_id=trilha_id)
    db.add(inscricao)
    await db.commit()
    await db.refresh(inscricao)
    return inscricao


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


@router.get("/{trilha_id}/progresso-detalhado")
async def progresso_trilha_detalhado(
    trilha_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    _: Usuario = Depends(require_permissao(Permissoes.TRILHA_VER_PROGRESSO)),
):
    result = await db.execute(
        select(InscricaoTrilha).where(
            InscricaoTrilha.usuario_id == current_user.id,
            InscricaoTrilha.trilha_id == trilha_id,
        )
    )
    inscricao = result.scalar_one_or_none()
    if not inscricao:
        raise HTTPException(status_code=404, detail="Inscricao nao encontrada nesta trilha")

    trilha_result = await db.execute(
        select(TrilhaAprendizagem)
        .where(TrilhaAprendizagem.id == trilha_id)
        .options(selectinload(TrilhaAprendizagem.cursos))
    )
    trilha = trilha_result.scalar_one_or_none()
    if not trilha:
        raise HTTPException(status_code=404, detail="Trilha nao encontrada")

    cursos_data = []
    for c in trilha.cursos:
        curso_insc = await db.execute(
            select(Inscricao).where(
                Inscricao.usuario_id == current_user.id,
                Inscricao.curso_id == c.id,
            )
        )
        ci = curso_insc.scalar_one_or_none()
        cursos_data.append({
            "curso_id": c.id,
            "titulo": c.titulo,
            "carga_horaria": c.carga_horaria,
            "inscrito": ci is not None,
            "status": ci.status if ci else "nao_inscrito",
            "progresso_pct": float(ci.progresso_pct) if ci and ci.progresso_pct else 0.0,
            "nota_final": float(ci.nota_final) if ci and ci.nota_final else None,
            "data_conclusao": ci.data_conclusao.isoformat() if ci and ci.data_conclusao else None,
        })

    return {
        "trilha_id": trilha.id,
        "titulo": trilha.titulo,
        "nivel": trilha.nivel,
        "carga_horaria_total": trilha.carga_horaria_total,
        "total_cursos": len(trilha.cursos),
        "cursos_concluidos": sum(1 for c in cursos_data if c["status"] == "concluido"),
        "cursos_inscritos": sum(1 for c in cursos_data if c["inscrito"]),
        "progresso_pct": float(inscricao.progresso_pct) if inscricao.progresso_pct else 0.0,
        "status": inscricao.status,
        "data_inscricao": inscricao.data_inscricao.isoformat(),
        "data_conclusao": inscricao.data_conclusao.isoformat() if inscricao.data_conclusao else None,
        "cursos": cursos_data,
    }


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
