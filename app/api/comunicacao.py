from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.comunicacao import ForumResposta, ForumTermoBloqueado, ForumTopico, MensagemChat
from app.models.curso import Curso
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
    curso = await db.get(Curso, curso_id)
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
    query = select(ForumTopico).where(ForumTopico.curso_id == curso_id)
    query = apply_search(query, [ForumTopico.titulo, ForumTopico.conteudo], q)
    total = await count_query(db, query)
    result = await db.execute(
        query.order_by(ForumTopico.fixado.desc(), ForumTopico.criado_em.desc()).offset(skip).limit(limit)
    )
    items = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)

    autores_ids = {t.autor_id for t in items}
    autores = {}
    if autores_ids:
        rows = await db.execute(select(Usuario).where(Usuario.id.in_(autores_ids)))
        autores = {u.id: u.nome_completo for u in rows.scalars().all()}

    return [
        ForumTopicoRead(
            **ForumTopicoRead.model_validate(t).model_dump(exclude={"autor_nome"}),
            autor_nome=autores.get(t.autor_id, ""),
        )
        for t in items
    ]


@router.post("/forum", response_model=ForumTopicoRead, status_code=status.HTTP_201_CREATED)
async def criar_topico(
    payload: ForumTopicoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.FORUM_CRIAR)),
):
    curso = await db.get(Curso, payload.curso_id)
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
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
    return ForumTopicoRead(
        **ForumTopicoRead.model_validate(topico).model_dump(exclude={"autor_nome"}),
        autor_nome=current_user.nome_completo,
    )


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
    return await _topico_com_autor(db, topico)


async def _topico_com_autor(db: AsyncSession, topico: ForumTopico) -> ForumTopicoRead:
    autor = await db.get(Usuario, topico.autor_id)
    return ForumTopicoRead(
        **ForumTopicoRead.model_validate(topico).model_dump(exclude={"autor_nome"}),
        autor_nome=autor.nome_completo if autor else "",
    )


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
    return await _topico_com_autor(db, topico)


@router.patch("/forum/topico/{topico_id}/fixar", response_model=ForumTopicoRead)
async def fixar_topico(
    topico_id: int,
    fixado: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_MODERAR)),
):
    result = await db.execute(select(ForumTopico).where(ForumTopico.id == topico_id))
    topico = result.scalar_one_or_none()
    if not topico:
        raise HTTPException(status_code=404, detail="Topico nao encontrado")
    topico.fixado = fixado
    await db.commit()
    await db.refresh(topico)
    return await _topico_com_autor(db, topico)


@router.patch("/forum/topico/{topico_id}/fechar", response_model=ForumTopicoRead)
async def fechar_topico(
    topico_id: int,
    fechado: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.FORUM_MODERAR)),
):
    result = await db.execute(select(ForumTopico).where(ForumTopico.id == topico_id))
    topico = result.scalar_one_or_none()
    if not topico:
        raise HTTPException(status_code=404, detail="Topico nao encontrado")
    topico.fechado = fechado
    await db.commit()
    await db.refresh(topico)
    return await _topico_com_autor(db, topico)


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
    respostas = result.scalars().all()

    autores_ids = {r.autor_id for r in respostas}
    autores = {}
    if autores_ids:
        rows = await db.execute(select(Usuario).where(Usuario.id.in_(autores_ids)))
        autores = {u.id: u.nome_completo for u in rows.scalars().all()}

    def _read(r: ForumResposta) -> ForumRespostaRead:
        return ForumRespostaRead(
            **ForumRespostaRead.model_validate(r).model_dump(exclude={"autor_nome", "respostas_filhas"}),
            autor_nome=autores.get(r.autor_id, ""),
        )

    por_id = {r.id: _read(r) for r in respostas}
    raizes: list[ForumRespostaRead] = []
    for r in respostas:
        item = por_id[r.id]
        if r.resposta_pai_id and r.resposta_pai_id in por_id:
            por_id[r.resposta_pai_id].respostas_filhas.append(item)
        else:
            raizes.append(item)
    return raizes


@router.post("/forum/respostas", response_model=ForumRespostaRead, status_code=status.HTTP_201_CREATED)
async def criar_resposta_forum(
    payload: ForumRespostaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.FORUM_CRIAR)),
):
    topico = await db.get(ForumTopico, payload.topico_id)
    if not topico:
        raise HTTPException(status_code=404, detail="Topico nao encontrado")
    if topico.fechado:
        raise HTTPException(status_code=403, detail="Topico fechado: novas respostas nao sao permitidas")
    if payload.resposta_pai_id is not None:
        pai = await db.get(ForumResposta, payload.resposta_pai_id)
        if not pai or pai.topico_id != topico.id:
            raise HTTPException(status_code=404, detail="Resposta pai nao encontrada neste topico")
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
    return ForumRespostaRead(
        **ForumRespostaRead.model_validate(resposta).model_dump(exclude={"autor_nome"}),
        autor_nome=current_user.nome_completo,
    )
