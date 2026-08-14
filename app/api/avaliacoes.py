import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.avaliacao import Alternativa, Avaliacao, Questao, RespostaParticipante, ResultadoAvaliacao
from app.models.curso import Curso, Inscricao, Unidade, Modulo, ProgressoUnidade
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.services.paginacao import apply_search, count_query
from app.services.gamificacao import atribuir_xp as gamificacao_xp
from app.services.rbac import Permissoes, has_permission
from app.schemas.avaliacao import (
    AlternativaCreate,
    AlternativaRead,
    AlternativaUpdate,
    AvaliacaoCreate,
    AvaliacaoRead,
    AvaliacaoResponderRead,
    AvaliacaoUpdate,
    CorrecaoPendenteInboxRead,
    CorrecaoPendenteRead,
    CorrigirRespostaRequest,
    EstatisticaQuestaoRead,
    EstatisticasAvaliacaoRead,
    QuestaoCreate,
    QuestaoRead,
    QuestaoUpdate,
    RespostaParticipanteCreate,
    RespostaParticipanteRead,
    ResultadoAvaliacaoCreate,
    ResultadoAvaliacaoRead,
    ResultadoFeedbackRead,
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


@router.get("/meus-resultados", response_model=list[ResultadoAvaliacaoRead])
async def meus_resultados(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result = await db.execute(
        select(ResultadoAvaliacao)
        .where(ResultadoAvaliacao.usuario_id == current_user.id)
        .order_by(ResultadoAvaliacao.realizado_em.desc())
    )
    return result.scalars().all()


@router.get("/correcoes-pendentes", response_model=list[CorrecaoPendenteInboxRead])
async def listar_correcoes_pendentes_agregado(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_AVALIAR)),
):
    """Inbox global de correcoes pendentes do instrutor (todas as avaliacoes).

    Respostas dissertativas sem pontuacao_atribuida, com contexto de
    curso/unidade/avaliacao. Se o usuario for instrutor de cursos especificos,
    filtra pelos cursos dele; caso contrario (administrador/gestor), retorna todas.
    """
    questoes_dissertativas = (
        await db.execute(select(Questao).where(Questao.tipo == "dissertativa"))
    ).scalars().all()
    questoes_por_id = {q.id: q for q in questoes_dissertativas}
    if not questoes_por_id:
        return []

    respostas = (
        await db.execute(
            select(RespostaParticipante)
            .where(
                RespostaParticipante.questao_id.in_(questoes_por_id.keys()),
                RespostaParticipante.pontuacao_atribuida.is_(None),
            )
            .order_by(RespostaParticipante.respondido_em.desc())
        )
    ).scalars().all()
    if not respostas:
        return []

    usuarios_ids = {r.usuario_id for r in respostas}
    usuarios = {}
    if usuarios_ids:
        rows = await db.execute(select(Usuario).where(Usuario.id.in_(usuarios_ids)))
        usuarios = {u.id: u.nome_completo for u in rows.scalars().all()}

    avaliacoes_ids = {questoes_por_id[r.questao_id].avaliacao_id for r in respostas}
    avaliacoes = {}
    if avaliacoes_ids:
        rows = await db.execute(select(Avaliacao).where(Avaliacao.id.in_(avaliacoes_ids)))
        avaliacoes = {a.id: a for a in rows.scalars().all()}

    unidades_ids = {a.unidade_id for a in avaliacoes.values() if a.unidade_id}
    unidades = {}
    if unidades_ids:
        rows = await db.execute(select(Unidade).where(Unidade.id.in_(unidades_ids)))
        unidades = {u.id: u for u in rows.scalars().all()}

    modulos_ids = {u.modulo_id for u in unidades.values()}
    modulos = {}
    if modulos_ids:
        rows = await db.execute(select(Modulo).where(Modulo.id.in_(modulos_ids)))
        modulos = {m.id: m for m in rows.scalars().all()}

    cursos_ids = {m.curso_id for m in modulos.values()}
    cursos = {}
    if cursos_ids:
        rows = await db.execute(select(Curso).where(Curso.id.in_(cursos_ids)))
        cursos = {c.id: c for c in rows.scalars().all()}

    if all(p.nome != "administrador_geral" for p in await _perfis_do_usuario(db, current_user.id)):
        cursos_do_instrutor = {c.id for c in cursos.values() if c.instrutor_id == current_user.id}
        if not cursos_do_instrutor:
            return []

    itens = []
    for r in respostas:
        questao = questoes_por_id[r.questao_id]
        avaliacao = avaliacoes.get(questao.avaliacao_id)
        unidade = unidades.get(avaliacao.unidade_id) if avaliacao and avaliacao.unidade_id else None
        modulo = modulos.get(unidade.modulo_id) if unidade else None
        curso = cursos.get(modulo.curso_id) if modulo else None
        itens.append(
            CorrecaoPendenteInboxRead(
                resposta_id=r.id,
                usuario_id=r.usuario_id,
                usuario_nome=usuarios.get(r.usuario_id),
                questao_id=r.questao_id,
                enunciado=questao.enunciado,
                resposta_texto=r.resposta_texto,
                pontuacao=questao.pontuacao,
                tentativa_num=r.tentativa_num,
                respondido_em=r.respondido_em,
                avaliacao_id=questao.avaliacao_id,
                avaliacao_titulo=avaliacao.titulo if avaliacao else "",
                curso_id=curso.id if curso else None,
                curso_titulo=curso.titulo if curso else None,
                unidade_titulo=unidade.titulo if unidade else None,
            )
        )
    return itens


async def _perfis_do_usuario(db: AsyncSession, usuario_id: uuid.UUID) -> list[Perfil]:
    result = await db.execute(
        select(Perfil).join(UsuarioPerfil).where(UsuarioPerfil.usuario_id == usuario_id)
    )
    return list(result.scalars().all())


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


@router.delete("/questoes/{questao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_questao(
    questao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_EXCLUIR)),
):
    result = await db.execute(select(Questao).where(Questao.id == questao_id))
    questao = result.scalar_one_or_none()
    if not questao:
        raise HTTPException(status_code=404, detail="Questao nao encontrada")
    await db.delete(questao)
    await db.commit()


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
                if not insc.scalars().first():
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
                if not insc.scalars().first():
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

    if avaliacao.tempo_limite_min:
        if payload.iniciado_em is None:
            raise HTTPException(
                status_code=422,
                detail="Campo iniciado_em obrigatorio quando a avaliacao tem tempo_limite_min",
            )
        agora = datetime.now(timezone.utc)
        if payload.iniciado_em > agora + timedelta(minutes=5):
            raise HTTPException(status_code=400, detail="iniciado_em nao pode estar no futuro")
        if (agora - payload.iniciado_em).total_seconds() > 24 * 3600:
            raise HTTPException(status_code=400, detail="iniciado_em muito antigo (mais de 24h)")

    if avaliacao.tempo_limite_min and payload.iniciado_em:
        elapsed = (datetime.now(timezone.utc) - payload.iniciado_em).total_seconds()
        if elapsed > avaliacao.tempo_limite_min * 60:
            raise HTTPException(
                status_code=400,
                detail=f"Tempo limite de {avaliacao.tempo_limite_min} minutos excedido",
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

    nota, aprovado = await calcular_nota(
        db,
        avaliacao,
        questoes_ids,
        respostas_alternativas,
        usuario_id=current_user.id,
        tentativa_num=tentativa_num,
    )

    tempo_gasto = None
    if payload.iniciado_em:
        tempo_gasto = int((datetime.now(timezone.utc) - payload.iniciado_em).total_seconds())

    if aprovado and avaliacao.unidade_id:
        from app.services.progresso import concluir_unidade

        try:
            await concluir_unidade(db, current_user.id, avaliacao.unidade_id, tempo_gasto or 0)
        except ValueError:
            pass

    resultado = ResultadoAvaliacao(
        usuario_id=current_user.id,
        avaliacao_id=avaliacao_id,
        nota=nota,
        aprovado=aprovado,
        tentativa_num=tentativa_num,
        tempo_gasto_seg=tempo_gasto,
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
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_RESPONDER)),
):
    data = payload.model_dump(exclude={"usuario_id"})
    resposta = RespostaParticipante(usuario_id=current_user.id, **data)
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
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_RESPONDER)),
):
    # Buscar avaliacao para nota_minima
    avaliacao = await db.get(Avaliacao, payload.avaliacao_id)
    if not avaliacao:
        raise HTTPException(status_code=404, detail="Avaliacao nao encontrada")

    # Buscar respostas do usuario para esta avaliacao + tentativa
    respostas = (
        await db.execute(
            select(RespostaParticipante).where(
                RespostaParticipante.usuario_id == current_user.id,
                RespostaParticipante.tentativa_num == payload.tentativa_num,
            )
        )
    ).scalars().all()

    respostas_ids = {r.questao_id for r in respostas if r.correta}
    respostas_questoes_ids = {r.questao_id for r in respostas}

    # Buscar questoes da avaliacao
    questoes = (
        await db.execute(
            select(Questao).where(Questao.avaliacao_id == payload.avaliacao_id)
        )
    ).scalars().all()

    pontuacao_total = sum(q.pontuacao for q in questoes if q.id in respostas_questoes_ids)
    pontuacao_obtida = sum(q.pontuacao for q in questoes if q.id in respostas_ids)

    nota = Decimal("0")
    aprovado = False
    if pontuacao_total > 0:
        nota = (pontuacao_obtida / pontuacao_total) * Decimal("100")
        nota = nota.quantize(Decimal("0.01"))
        aprovado = nota >= avaliacao.nota_minima

    resultado = ResultadoAvaliacao(
        usuario_id=current_user.id,
        avaliacao_id=payload.avaliacao_id,
        nota=nota,
        aprovado=aprovado,
        tentativa_num=payload.tentativa_num,
        tempo_gasto_seg=payload.tempo_gasto_seg,
    )
    db.add(resultado)

    await gamificacao_xp(db, usuario_id=current_user.id, evento="avaliacao_respondida", referencia_id=payload.avaliacao_id)

    await db.commit()
    await db.refresh(resultado)
    return resultado


@router.get("/{avaliacao_id}/resultado/{tentativa}", response_model=ResultadoFeedbackRead)
async def obter_resultado_com_feedback(
    avaliacao_id: int,
    tentativa: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result = await db.execute(
        select(ResultadoAvaliacao).where(
            ResultadoAvaliacao.avaliacao_id == avaliacao_id,
            ResultadoAvaliacao.tentativa_num == tentativa,
            ResultadoAvaliacao.usuario_id == current_user.id,
        )
    )
    resultado = result.scalar_one_or_none()
    if not resultado:
        raise HTTPException(status_code=404, detail="Resultado nao encontrado para esta tentativa")

    respostas = (
        await db.execute(
            select(RespostaParticipante).where(
                RespostaParticipante.usuario_id == current_user.id,
                RespostaParticipante.tentativa_num == tentativa,
            )
        )
    ).scalars().all()

    questoes = (
        await db.execute(select(Questao).where(Questao.avaliacao_id == avaliacao_id).order_by(Questao.ordem))
    ).scalars().all()

    respostas_por_questao = {r.questao_id: r for r in respostas}
    questoes_read = []
    for q in questoes:
        resp = respostas_por_questao.get(q.id)
        alternativas = (
            await db.execute(
                select(Alternativa).where(Alternativa.questao_id == q.id).order_by(Alternativa.ordem)
            )
        ).scalars().all()

        from app.schemas.avaliacao import ResultadoFeedbackAlternativa

        alternativas_read = []
        pontuacao_obtida = Decimal("0")
        for a in alternativas:
            escolhida = resp is not None and resp.alternativa_id == a.id
            alternativas_read.append(
                ResultadoFeedbackAlternativa(
                    id=a.id, texto=a.texto, correta=a.correta, escolhida=escolhida, ordem=a.ordem
                )
            )
            if escolhida and a.correta:
                pontuacao_obtida += q.pontuacao

        if q.tipo == "dissertativa" and resp is not None and resp.pontuacao_atribuida is not None:
            pontuacao_obtida = resp.pontuacao_atribuida

        from app.schemas.avaliacao import ResultadoFeedbackQuestao

        questoes_read.append(
            ResultadoFeedbackQuestao(
                id=q.id,
                enunciado=q.enunciado,
                tipo=q.tipo,
                pontuacao=q.pontuacao,
                pontuacao_obtida=pontuacao_obtida,
                resposta_texto=resp.resposta_texto if resp is not None else None,
                pontuacao_atribuida=resp.pontuacao_atribuida if resp is not None else None,
                alternativas=alternativas_read,
                explicacao=q.explicacao,
            )
        )

    from app.schemas.avaliacao import ResultadoFeedbackRead

    return ResultadoFeedbackRead(
        resultado_id=resultado.id,
        avaliacao_id=avaliacao_id,
        nota=resultado.nota,
        aprovado=resultado.aprovado,
        tentativa_num=resultado.tentativa_num,
        tempo_gasto_seg=resultado.tempo_gasto_seg,
        realizado_em=resultado.realizado_em,
        questoes=questoes_read,
    )


@router.get("/{avaliacao_id}/resultados", response_model=list[ResultadoAvaliacaoRead])
async def listar_resultados_avaliacao(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result_perfis = await db.execute(select(Perfil).join(UsuarioPerfil).where(UsuarioPerfil.usuario_id == current_user.id))
    pode_avaliar = any(has_permission(p.nome, Permissoes.AVALIACAO_AVALIAR) for p in result_perfis.scalars().all())

    where_clause = [ResultadoAvaliacao.avaliacao_id == avaliacao_id]
    if not pode_avaliar:
        where_clause.append(ResultadoAvaliacao.usuario_id == current_user.id)

    result = await db.execute(
        select(ResultadoAvaliacao)
        .where(*where_clause)
        .order_by(ResultadoAvaliacao.realizado_em.desc())
    )
    return result.scalars().all()


@router.get("/{avaliacao_id}/estatisticas", response_model=EstatisticasAvaliacaoRead)
async def estatisticas_avaliacao(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    result = await db.execute(select(ResultadoAvaliacao).where(ResultadoAvaliacao.avaliacao_id == avaliacao_id))
    resultados = result.scalars().all()

    total = len(resultados)
    aprovados = sum(1 for r in resultados if r.aprovado)
    media = float(sum(r.nota for r in resultados) / total) if total > 0 else 0.0
    taxa = (aprovados / total * 100) if total > 0 else 0.0

    return EstatisticasAvaliacaoRead(
        total_tentativas=total,
        total_aprovados=aprovados,
        media_nota=round(media, 2),
        taxa_aprovacao=round(taxa, 2),
    )


@router.get("/{avaliacao_id}/estatisticas/questoes", response_model=list[EstatisticaQuestaoRead])
async def estatisticas_questoes(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    """Estatisticas por questao: quantos responderam, acertaram e taxa de acerto.

    - multipla_escolha/verdadeiro_falso: 'correta' vem da correcao automatica.
    - dissertativa: 'correta' e preenchido na correcao manual; respostas sem
      pontuacao_atribuida contam em 'aguardando_correcao' e nao entram na taxa.
    """
    questoes = (
        await db.execute(select(Questao).where(Questao.avaliacao_id == avaliacao_id).order_by(Questao.ordem))
    ).scalars().all()
    if not questoes:
        return []

    respostas = (
        await db.execute(
            select(RespostaParticipante)
            .join(Questao, Questao.id == RespostaParticipante.questao_id)
            .where(Questao.avaliacao_id == avaliacao_id)
        )
    ).scalars().all()

    stats: dict[int, dict] = {}
    for q in questoes:
        stats[q.id] = {
            "questao_id": q.id,
            "enunciado": q.enunciado,
            "tipo": q.tipo,
            "pontuacao": q.pontuacao,
            "respondida": 0,
            "acertos": 0,
            "aguardando_correcao": 0,
        }

    for r in respostas:
        if r.questao_id not in stats:
            continue
        st = stats[r.questao_id]
        st["respondida"] += 1
        if r.pontuacao_atribuida is None and r.alternativa_id is None:
            st["aguardando_correcao"] += 1
        elif r.correta:
            st["acertos"] += 1

    resultado = []
    for q in questoes:
        st = stats[q.id]
        corrigidas = st["respondida"] - st["aguardando_correcao"]
        taxa = (st["acertos"] / corrigidas * 100) if corrigidas > 0 else 0.0
        st["taxa_acerto"] = round(taxa, 2)
        resultado.append(EstatisticaQuestaoRead(**st))
    return resultado


# --- Correção manual de dissertativas ---


@router.get("/{avaliacao_id}/correcoes-pendentes", response_model=list[CorrecaoPendenteRead])
async def listar_correcoes_pendentes(
    avaliacao_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_AVALIAR)),
):
    avaliacao = await db.get(Avaliacao, avaliacao_id)
    if not avaliacao:
        raise HTTPException(status_code=404, detail="Avaliacao nao encontrada")

    questoes = (
        await db.execute(select(Questao).where(Questao.avaliacao_id == avaliacao_id))
    ).scalars().all()
    dissertativas = {q.id: q for q in questoes if q.tipo == "dissertativa"}
    if not dissertativas:
        return []

    respostas = (
        await db.execute(
            select(RespostaParticipante)
            .where(
                RespostaParticipante.questao_id.in_(dissertativas.keys()),
                RespostaParticipante.pontuacao_atribuida.is_(None),
            )
            .order_by(RespostaParticipante.respondido_em.desc())
        )
    ).scalars().all()

    usuarios_ids = {r.usuario_id for r in respostas}
    usuarios = {}
    if usuarios_ids:
        rows = await db.execute(select(Usuario).where(Usuario.id.in_(usuarios_ids)))
        usuarios = {u.id: u.nome_completo for u in rows.scalars().all()}

    return [
        CorrecaoPendenteRead(
            resposta_id=r.id,
            usuario_id=r.usuario_id,
            usuario_nome=usuarios.get(r.usuario_id),
            questao_id=r.questao_id,
            enunciado=dissertativas[r.questao_id].enunciado,
            resposta_texto=r.resposta_texto,
            pontuacao=dissertativas[r.questao_id].pontuacao,
            tentativa_num=r.tentativa_num,
            respondido_em=r.respondido_em,
        )
        for r in respostas
    ]


@router.patch("/respostas/{resposta_id}/corrigir", response_model=RespostaParticipanteRead)
async def corrigir_resposta_dissertativa(
    resposta_id: int,
    payload: CorrigirRespostaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_AVALIAR)),
):
    resposta = await db.get(RespostaParticipante, resposta_id)
    if not resposta:
        raise HTTPException(status_code=404, detail="Resposta nao encontrada")

    questao = await db.get(Questao, resposta.questao_id)
    if not questao or questao.tipo != "dissertativa":
        raise HTTPException(status_code=400, detail="Correcao manual so e permitida para questoes dissertativas")

    if payload.pontuacao_atribuida < 0 or payload.pontuacao_atribuida > questao.pontuacao:
        raise HTTPException(
            status_code=400,
            detail=f"pontuacao_atribuida deve estar entre 0 e {questao.pontuacao}",
        )

    resposta.pontuacao_atribuida = payload.pontuacao_atribuida
    resposta.correta = payload.pontuacao_atribuida > 0
    resposta.corrigida_por = current_user.id
    resposta.corrigida_em = datetime.now(timezone.utc)

    avaliacao = await db.get(Avaliacao, questao.avaliacao_id)
    resultado = (
        await db.execute(
            select(ResultadoAvaliacao).where(
                ResultadoAvaliacao.avaliacao_id == questao.avaliacao_id,
                ResultadoAvaliacao.usuario_id == resposta.usuario_id,
                ResultadoAvaliacao.tentativa_num == resposta.tentativa_num,
            )
        )
    ).scalar_one_or_none()

    if resultado is not None:
        from app.services.avaliacao import calcular_nota

        questoes_db = (
            await db.execute(select(Questao).where(Questao.avaliacao_id == questao.avaliacao_id))
        ).scalars().all()
        questoes_ids = {q.id for q in questoes_db}

        respostas_usuario = (
            await db.execute(
                select(RespostaParticipante).where(
                    RespostaParticipante.usuario_id == resposta.usuario_id,
                    RespostaParticipante.tentativa_num == resposta.tentativa_num,
                )
            )
        ).scalars().all()

        respostas_alternativas = {}
        for r in respostas_usuario:
            if r.alternativa_id is not None:
                respostas_alternativas[r.questao_id] = r.alternativa_id

        nota, aprovado = await calcular_nota(
            db,
            avaliacao,
            questoes_ids,
            respostas_alternativas,
            usuario_id=resposta.usuario_id,
            tentativa_num=resposta.tentativa_num,
        )
        resultado.nota = nota
        resultado.aprovado = aprovado

    await db.commit()
    await db.refresh(resposta)
    return resposta


@router.get("/resultados/{usuario_id}", response_model=list[ResultadoAvaliacaoRead])
async def listar_resultados_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AVALIACAO_VISUALIZAR)),
):
    if current_user.id != usuario_id:
        result_perfis = await db.execute(
            select(Perfil).join(UsuarioPerfil).where(UsuarioPerfil.usuario_id == current_user.id)
        )
        pode_avaliar = any(has_permission(p.nome, Permissoes.AVALIACAO_AVALIAR) for p in result_perfis.scalars().all())
        if not pode_avaliar:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você só pode visualizar seus próprios resultados.",
            )

    result = await db.execute(select(ResultadoAvaliacao).where(ResultadoAvaliacao.usuario_id == usuario_id))
    return result.scalars().all()
