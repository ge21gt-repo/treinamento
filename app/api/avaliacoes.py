import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.avaliacao import Alternativa, Avaliacao, Questao, RespostaParticipante, ResultadoAvaliacao
from app.models.curso import Inscricao, Unidade, Modulo
from app.models.usuario import Usuario
from app.services.paginacao import apply_search, count_query
from app.services.rbac import Permissoes
from app.schemas.avaliacao import (
    AlternativaCreate,
    AlternativaRead,
    AlternativaUpdate,
    AvaliacaoCreate,
    AvaliacaoRead,
    AvaliacaoResponderRead,
    AvaliacaoUpdate,
    QuestaoCreate,
    QuestaoRead,
    QuestaoUpdate,
    RespostaParticipanteCreate,
    RespostaParticipanteRead,
    ResultadoAvaliacaoCreate,
    ResultadoAvaliacaoRead,
    SubmeterAvaliacaoRequest,
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
    questao = await db.get(Questao, payload.questao_id)
    if not questao:
        raise HTTPException(status_code=404, detail="Questao nao encontrada")
    if questao.tipo == "verdadeiro_falso":
        count = await db.scalar(
            select(func.count()).where(Alternativa.questao_id == payload.questao_id)
        )
        if count >= 2:
            raise HTTPException(
                status_code=400,
                detail="Questao verdadeiro_falso ja possui 2 alternativas (verdadeiro/falso)",
            )
    alternativa = Alternativa(**payload.model_dump())
    db.add(alternativa)
    await db.commit()
    await db.refresh(alternativa)
    return alternativa


@router.patch("/alternativas/{alternativa_id}", response_model=AlternativaRead)
async def atualizar_alternativa(
    alternativa_id: int,
    payload: AlternativaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_EDITAR)),
):
    result = await db.execute(select(Alternativa).where(Alternativa.id == alternativa_id))
    alternativa = result.scalar_one_or_none()
    if not alternativa:
        raise HTTPException(status_code=404, detail="Alternativa nao encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(alternativa, field, value)
    await db.commit()
    await db.refresh(alternativa)
    return alternativa


@router.delete("/alternativas/{alternativa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_alternativa(
    alternativa_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_EXCLUIR)),
):
    result = await db.execute(select(Alternativa).where(Alternativa.id == alternativa_id))
    alternativa = result.scalar_one_or_none()
    if not alternativa:
        raise HTTPException(status_code=404, detail="Alternativa nao encontrada")
    await db.delete(alternativa)
    await db.commit()


# --- Realizacao da avaliacao ---


@router.get("/{avaliacao_id}/responder", response_model=AvaliacaoResponderRead)
async def responder_avaliacao(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_RESPONDER)),
):
    result = await db.execute(select(Avaliacao).where(Avaliacao.id == avaliacao_id))
    avaliacao = result.scalar_one_or_none()
    if not avaliacao:
        raise HTTPException(status_code=404, detail="Avaliacao nao encontrada")
    if not avaliacao.ativa:
        raise HTTPException(status_code=400, detail="Avaliacao nao esta ativa")

    if avaliacao.unidade_id:
        unidade = await db.get(Unidade, avaliacao.unidade_id)
        if unidade:
            modulo = await db.get(Modulo, unidade.modulo_id)
            if modulo:
                insc = await db.execute(
                    select(Inscricao).where(
                        Inscricao.curso_id == modulo.curso_id,
                        Inscricao.usuario_id == current_user.id,
                    )
                )
                if not insc.scalar_one_or_none():
                    raise HTTPException(
                        status_code=403, detail="Usuario nao esta inscrito no curso desta avaliacao"
                    )

    questoes = (
        await db.execute(select(Questao).where(Questao.avaliacao_id == avaliacao_id).order_by(Questao.ordem))
    ).scalars().all()

    from app.schemas.avaliacao import AlternativaResponderRead, QuestaoResponderRead

    questoes_read = []
    for q in questoes:
        alternativas = (
            await db.execute(
                select(Alternativa).where(Alternativa.questao_id == q.id).order_by(Alternativa.ordem)
            )
        ).scalars().all()
        questoes_read.append(
            QuestaoResponderRead(
                id=q.id,
                avaliacao_id=q.avaliacao_id,
                enunciado=q.enunciado,
                tipo=q.tipo,
                pontuacao=q.pontuacao,
                ordem=q.ordem,
                alternativas=[
                    AlternativaResponderRead(
                        id=a.id, questao_id=a.questao_id, texto=a.texto, ordem=a.ordem
                    )
                    for a in alternativas
                ],
            )
        )

    return AvaliacaoResponderRead(
        id=avaliacao.id,
        titulo=avaliacao.titulo,
        descricao=avaliacao.descricao,
        tipo=avaliacao.tipo,
        tentativas_max=avaliacao.tentativas_max,
        tempo_limite_min=avaliacao.tempo_limite_min,
        questoes=questoes_read,
    )


@router.post("/{avaliacao_id}/submeter", status_code=status.HTTP_201_CREATED)
async def submeter_avaliacao(
    avaliacao_id: int,
    payload: SubmeterAvaliacaoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_RESPONDER)),
):
    result = await db.execute(select(Avaliacao).where(Avaliacao.id == avaliacao_id))
    avaliacao = result.scalar_one_or_none()
    if not avaliacao:
        raise HTTPException(status_code=404, detail="Avaliacao nao encontrada")
    if not avaliacao.ativa:
        raise HTTPException(status_code=400, detail="Avaliacao nao esta ativa")

    if avaliacao.unidade_id:
        unidade = await db.get(Unidade, avaliacao.unidade_id)
        if unidade:
            modulo = await db.get(Modulo, unidade.modulo_id)
            if modulo:
                insc = await db.execute(
                    select(Inscricao).where(
                        Inscricao.curso_id == modulo.curso_id,
                        Inscricao.usuario_id == current_user.id,
                    )
                )
                if not insc.scalar_one_or_none():
                    raise HTTPException(
                        status_code=403, detail="Usuario nao esta inscrito no curso desta avaliacao"
                    )

    tentativas = await db.scalar(
        select(func.count()).where(
            ResultadoAvaliacao.avaliacao_id == avaliacao_id,
            ResultadoAvaliacao.usuario_id == current_user.id,
        )
    )
    if tentativas >= avaliacao.tentativas_max:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {avaliacao.tentativas_max} tentativas atingido",
        )

    tentativa_num = tentativas + 1

    questoes_ids = {r.questao_id for r in payload.respostas}
    questoes_db = (
        await db.execute(select(Questao).where(Questao.avaliacao_id == avaliacao_id))
    ).scalars().all()
    questoes_validas = {q.id for q in questoes_db}
    invalidas = questoes_ids - questoes_validas
    if invalidas:
        raise HTTPException(
            status_code=400,
            detail=f"Questoes {invalidas} nao pertencem a esta avaliacao",
        )

    respostas_alternativas = {}
    for r in payload.respostas:
        resposta = RespostaParticipante(
            usuario_id=current_user.id,
            questao_id=r.questao_id,
            alternativa_id=r.alternativa_id,
            resposta_texto=r.resposta_texto,
            tentativa_num=tentativa_num,
        )
        if r.alternativa_id:
            alt = await db.get(Alternativa, r.alternativa_id)
            if alt:
                resposta.correta = alt.correta
                respostas_alternativas[r.questao_id] = r.alternativa_id
        db.add(resposta)

    from app.services.avaliacao import calcular_nota

    nota, aprovado = await calcular_nota(db, avaliacao, questoes_ids, respostas_alternativas)

    resultado = ResultadoAvaliacao(
        usuario_id=current_user.id,
        avaliacao_id=avaliacao_id,
        nota=nota,
        aprovado=aprovado,
        tentativa_num=tentativa_num,
    )
    db.add(resultado)
    await db.commit()
    await db.refresh(resultado)

    return {"message": "Avaliacao submetida com sucesso", "resultado_id": resultado.id, "tentativa": tentativa_num, "nota": float(nota), "aprovado": aprovado}


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
