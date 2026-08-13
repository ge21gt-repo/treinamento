from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.comunicacao import ForumResposta, ForumTermoBloqueado, ForumTopico, MensagemChat
from app.models.usuario import Usuario
from app.services.paginacao import apply_search, count_query
from app.services.moderacao import checar_conteudo
from app.services.rbac import Permissoes
from app.schemas.comunicacao import (
    ForumRespostaCreate,
    ForumRespostaRead,
    ForumTermoBloqueadoCreate,
    ForumTermoBloqueadoRead,
    ForumTopicoCreate,
    ForumTopicoRead,
    ForumTopicoUpdate,
    MensagemChatCreate,
    MensagemChatRead,
)

router = APIRouter(prefix="/comunicacao", tags=["Comunicacao"])


# --- Chat ---


@router.post("/chat", response_model=MensagemChatRead, status_code=status.HTTP_201_CREATED)
async def enviar_mensagem(
    payload: MensagemChatCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CHAT_ENVIAR)),
):
    msg = MensagemChat(**payload.model_dump(), usuario_id=current_user.id)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


@router.get("/chat/{sessao_id}", response_model=list[MensagemChatRead])
async def listar_mensagens(
    sessao_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.CHAT_VISUALIZAR)),
):
    query = (
        select(MensagemChat)
        .where(MensagemChat.sessao_id == sessao_id)
    )
    total = await count_query(db, query)
    result = await db.execute(
        query.order_by(MensagemChat.enviado_em).offset(skip).limit(limit)
    )
    items = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return items


# --- Forum ---


# --- Termos bloqueados (moderacao US-14) ---


@router.get("/forum/termos-bloqueados", response_model=list[ForumTermoBloqueadoRead])
async def listar_termos_bloqueados(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_MODERAR)),
):
    result = await db.execute(select(ForumTermoBloqueado).order_by(ForumTermoBloqueado.categoria, ForumTermoBloqueado.termo))
    return result.scalars().all()


@router.post("/forum/termos-bloqueados", response_model=ForumTermoBloqueadoRead, status_code=status.HTTP_201_CREATED)
async def criar_termo_bloqueado(
    payload: ForumTermoBloqueadoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_MODERAR)),
):
    termo = payload.termo.strip().lower()
    if not termo:
        raise HTTPException(status_code=422, detail="Termo nao pode ser vazio")
    existente = await db.execute(select(ForumTermoBloqueado).where(ForumTermoBloqueado.termo == termo))
    if existente.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Termo ja cadastrado")
    novo = ForumTermoBloqueado(termo=termo, categoria=payload.categoria)
    db.add(novo)
    await db.commit()
    await db.refresh(novo)
    return novo


@router.delete("/forum/termos-bloqueados/{termo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_termo_bloqueado(
    termo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_MODERAR)),
):
    result = await db.execute(select(ForumTermoBloqueado).where(ForumTermoBloqueado.id == termo_id))
    termo = result.scalar_one_or_none()
    if not termo:
        raise HTTPException(status_code=404, detail="Termo nao encontrado")
    await db.delete(termo)
    await db.commit()


@router.get("/forum/{curso_id}", response_model=list[ForumTopicoRead])
async def listar_topicos(
    curso_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, description="Busca textual por titulo ou conteudo"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_VISUALIZAR)),
):
    query = select(ForumTopico).where(ForumTopico.curso_id == curso_id)
    query = apply_search(query, [ForumTopico.titulo, ForumTopico.conteudo], q)
    total = await count_query(db, query)
    result = await db.execute(
        query.order_by(ForumTopico.fixado.desc(), ForumTopico.criado_em.desc()).offset(skip).limit(limit)
    )
    items = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("/forum", response_model=ForumTopicoRead, status_code=status.HTTP_201_CREATED)
async def criar_topico(
    payload: ForumTopicoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.FORUM_CRIAR)),
):
    termo = await checar_conteudo(db, f"{payload.titulo} {payload.conteudo}")
    if termo:
        raise HTTPException(
            status_code=422,
            detail=f"Conteudo bloqueado: contem o termo '{termo}'",
        )
    topico = ForumTopico(**payload.model_dump(), autor_id=current_user.id)
    db.add(topico)
    await db.commit()
    await db.refresh(topico)
    return topico


@router.get("/forum/topico/{topico_id}", response_model=ForumTopicoRead)
async def obter_topico(
    topico_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_VISUALIZAR)),
):
    result = await db.execute(select(ForumTopico).where(ForumTopico.id == topico_id))
    topico = result.scalar_one_or_none()
    if not topico:
        raise HTTPException(status_code=404, detail="Topico nao encontrado")
    return topico


@router.patch("/forum/topico/{topico_id}", response_model=ForumTopicoRead)
async def atualizar_topico(
    topico_id: int,
    payload: ForumTopicoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_EDITAR)),
):
    result = await db.execute(select(ForumTopico).where(ForumTopico.id == topico_id))
    topico = result.scalar_one_or_none()
    if not topico:
        raise HTTPException(status_code=404, detail="Topico nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(topico, field, value)
    await db.commit()
    await db.refresh(topico)
    return topico


@router.delete("/forum/topico/{topico_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_topico(
    topico_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_EXCLUIR)),
):
    result = await db.execute(select(ForumTopico).where(ForumTopico.id == topico_id))
    topico = result.scalar_one_or_none()
    if not topico:
        raise HTTPException(status_code=404, detail="Topico nao encontrado")
    await db.delete(topico)
    await db.commit()


# --- Forum Respostas ---


@router.get("/forum/topico/{topico_id}/respostas", response_model=list[ForumRespostaRead])
async def listar_respostas(
    topico_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_VISUALIZAR)),
):
    result = await db.execute(
        select(ForumResposta).where(ForumResposta.topico_id == topico_id).order_by(ForumResposta.criado_em)
    )
    return result.scalars().all()


@router.post("/forum/respostas", response_model=ForumRespostaRead, status_code=status.HTTP_201_CREATED)
async def criar_resposta_forum(
    payload: ForumRespostaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.FORUM_CRIAR)),
):
    termo = await checar_conteudo(db, payload.conteudo)
    if termo:
        raise HTTPException(
            status_code=422,
            detail=f"Conteudo bloqueado: contem o termo '{termo}'",
        )
    resposta = ForumResposta(**payload.model_dump(), autor_id=current_user.id)
    db.add(resposta)
    await db.commit()
    await db.refresh(resposta)
    return resposta
