import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.avaliacao import Alternativa, Avaliacao, Questao, RespostaParticipante, ResultadoAvaliacao
from app.models.usuario import Usuario
from app.services.paginacao import apply_search, count_query
from app.services.rbac import Permissoes
from app.schemas.avaliacao import (
    AlternativaCreate,
    AlternativaRead,
    AvaliacaoCreate,
    AvaliacaoRead,
    AvaliacaoUpdate,
    QuestaoCreate,
    QuestaoRead,
    QuestaoUpdate,
    RespostaParticipanteCreate,
    RespostaParticipanteRead,
    ResultadoAvaliacaoCreate,
    ResultadoAvaliacaoRead,
)

router = APIRouter(prefix="/avaliacoes", tags=["Avaliacoes"])


@router.get("", response_model=list[AvaliacaoRead])
async def listar_avaliacoes(
    unidade_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, description="Busca textual por titulo"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    query = select(Avaliacao)
    if unidade_id is not None:
        query = query.where(Avaliacao.unidade_id == unidade_id)
    query = apply_search(query, [Avaliacao.titulo], q)
    total = await count_query(db, query)
    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("", response_model=AvaliacaoRead, status_code=status.HTTP_201_CREATED)
async def criar_avaliacao(
    payload: AvaliacaoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_CRIAR)),
):
    avaliacao = Avaliacao(**payload.model_dump())
    db.add(avaliacao)
    await db.commit()
    await db.refresh(avaliacao)
    return avaliacao


@router.get("/{avaliacao_id}", response_model=AvaliacaoRead)
async def obter_avaliacao(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result = await db.execute(select(Avaliacao).where(Avaliacao.id == avaliacao_id))
    avaliacao = result.scalar_one_or_none()
    if not avaliacao:
        raise HTTPException(status_code=404, detail="Avaliacao nao encontrada")
    return avaliacao


@router.patch("/{avaliacao_id}", response_model=AvaliacaoRead)
async def atualizar_avaliacao(
    avaliacao_id: int,
    payload: AvaliacaoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_EDITAR)),
):
    result = await db.execute(select(Avaliacao).where(Avaliacao.id == avaliacao_id))
    avaliacao = result.scalar_one_or_none()
    if not avaliacao:
        raise HTTPException(status_code=404, detail="Avaliacao nao encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(avaliacao, field, value)
    await db.commit()
    await db.refresh(avaliacao)
    return avaliacao


@router.delete("/{avaliacao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_avaliacao(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_EXCLUIR)),
):
    result = await db.execute(select(Avaliacao).where(Avaliacao.id == avaliacao_id))
    avaliacao = result.scalar_one_or_none()
    if not avaliacao:
        raise HTTPException(status_code=404, detail="Avaliacao nao encontrada")
    await db.delete(avaliacao)
    await db.commit()


# --- Questoes ---


@router.get("/{avaliacao_id}/questoes", response_model=list[QuestaoRead])
async def listar_questoes(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result = await db.execute(select(Questao).where(Questao.avaliacao_id == avaliacao_id).order_by(Questao.ordem))
    return result.scalars().all()


@router.post("/questoes", response_model=QuestaoRead, status_code=status.HTTP_201_CREATED)
async def criar_questao(
    payload: QuestaoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_CRIAR)),
):
    questao = Questao(**payload.model_dump())
    db.add(questao)
    await db.commit()
    await db.refresh(questao)
    return questao


@router.patch("/questoes/{questao_id}", response_model=QuestaoRead)
async def atualizar_questao(
    questao_id: int,
    payload: QuestaoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_EDITAR)),
):
    result = await db.execute(select(Questao).where(Questao.id == questao_id))
    questao = result.scalar_one_or_none()
    if not questao:
        raise HTTPException(status_code=404, detail="Questao nao encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(questao, field, value)
    await db.commit()
    await db.refresh(questao)
    return questao


# --- Alternativas ---


@router.get("/questoes/{questao_id}/alternativas", response_model=list[AlternativaRead])
async def listar_alternativas(
    questao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result = await db.execute(
        select(Alternativa).where(Alternativa.questao_id == questao_id).order_by(Alternativa.ordem)
    )
    return result.scalars().all()


@router.post("/alternativas", response_model=AlternativaRead, status_code=status.HTTP_201_CREATED)
async def criar_alternativa(
    payload: AlternativaCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_CRIAR)),
):
    alternativa = Alternativa(**payload.model_dump())
    db.add(alternativa)
    await db.commit()
    await db.refresh(alternativa)
    return alternativa


# --- Respostas ---


@router.post("/respostas", response_model=RespostaParticipanteRead, status_code=status.HTTP_201_CREATED)
async def registrar_resposta(
    payload: RespostaParticipanteCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_RESPONDER)),
):
    resposta = RespostaParticipante(**payload.model_dump())
    if resposta.alternativa_id:
        alt = await db.execute(select(Alternativa).where(Alternativa.id == resposta.alternativa_id))
        alternativa = alt.scalar_one_or_none()
        if alternativa:
            resposta.correta = alternativa.correta
    db.add(resposta)
    await db.commit()
    await db.refresh(resposta)
    return resposta


# --- Resultados ---


@router.post("/resultados", response_model=ResultadoAvaliacaoRead, status_code=status.HTTP_201_CREATED)
async def registrar_resultado(
    payload: ResultadoAvaliacaoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_RESPONDER)),
):
    resultado = ResultadoAvaliacao(**payload.model_dump())
    db.add(resultado)
    await db.commit()
    await db.refresh(resultado)
    return resultado


@router.get("/resultados/{usuario_id}", response_model=list[ResultadoAvaliacaoRead])
async def listar_resultados_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result = await db.execute(select(ResultadoAvaliacao).where(ResultadoAvaliacao.usuario_id == usuario_id))
    return result.scalars().all()
