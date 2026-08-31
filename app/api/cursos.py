import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_permissao
from app.database import async_session, get_db
from app.models.conteudo import Conteudo, EntregaAtividade
from app.models.curso import AulaSincrona, Curso, Inscricao, MensagemAula, MensagemCurso, Modulo, PresencaAula, ProgressoUnidade, Unidade
from app.models.usuario import Usuario
from app.services.paginacao import apply_search, count_query
from app.services.storage import resolve_file_url
from app.schemas.curso import (
    AcessarAulaRequest,
    AcessarAulaResponse,
    AulaSincronaCreate,
    AulaSincronaRead,
    AulaSincronaUpdate,
    CursoArvoreItem,
    CursoArvoreRead,
    CursoCreate,
    CursoRead,
    CursoUpdate,
    InscricaoCreate,
    InscricaoRead,
    MensagemAulaCreate,
    MensagemAulaRead,
    ModuloArvoreRead,
    ModuloCreate,
    ModuloRead,
    ModuloUpdate,
    PresencaAulaRead,
    PresencaConsultaItem,
    PresencaRegistroRead,
    PresencaResumoRead,
    ProcessarGravacaoResponse,
    ProgressoUnidadeCreate,
    ProgressoUnidadeRead,
    ProgressoUnidadeUpdate,
    ReorderItem,
    UnidadeCreate,
    UnidadeRead,
    UnidadeUpdate,
)
from app.services import progresso as progresso_service
from app.services import teams as teams_service
from app.services.gamificacao import atribuir_xp as gamificacao_xp
from app.services.rbac import Permissoes

router = APIRouter(prefix="/cursos", tags=["Cursos"])


def _gerar_codigo_acesso() -> str:
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


# --- Cursos ---


@router.get("", response_model=list[CursoRead])
async def listar_cursos(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    trilha_id: int | None = Query(None),
    q: str | None = Query(None, description="Busca textual por titulo"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(get_current_user),
):
    query = select(Curso)
    if trilha_id is not None:
        query = query.where(Curso.trilha_id == trilha_id)
    query = apply_search(query, [Curso.titulo], q)
    total = await count_query(db, query)
    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("", response_model=CursoRead, status_code=status.HTTP_201_CREATED)
async def criar_curso(
    payload: CursoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_CRIAR)),
):
    if payload.pre_requisito_curso_id:
        result = await db.execute(select(Curso).where(Curso.id == payload.pre_requisito_curso_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Curso pre-requisito nao encontrado")
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
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_EDITAR)),
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
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_EXCLUIR)),
):
    result = await db.execute(select(Curso).where(Curso.id == curso_id))
    curso = result.scalar_one_or_none()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
    await db.delete(curso)
    await db.commit()


@router.get("/{curso_id}/arvore", response_model=CursoArvoreRead)
async def arvore_curso(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Curso).where(Curso.id == curso_id).options(selectinload(Curso.modulos).selectinload(Modulo.unidades))
    )
    curso = result.scalar_one_or_none()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
    modulos = [
        ModuloArvoreRead(
            id=m.id,
            titulo=m.titulo,
            ordem=m.ordem,
            unidades=[
                CursoArvoreItem(
                    id=u.id,
                    titulo=u.titulo,
                    tipo=u.tipo,
                    ordem=u.ordem,
                    conteudo_url=u.conteudo_url,
                    url_externa=u.url_externa,
                )
                for u in m.unidades
            ],
        )
        for m in sorted(curso.modulos, key=lambda x: x.ordem)
    ]
    return CursoArvoreRead(id=curso.id, titulo=curso.titulo, modulos=modulos)


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
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_MODULO_CRIAR)),
):
    modulo = Modulo(**payload.model_dump())
    db.add(modulo)
    await db.commit()
    await db.refresh(modulo)
    return modulo


@router.patch("/modulos/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reordenar_modulos(
    payload: list[ReorderItem],
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_MODULO_EDITAR)),
):
    ids = [item.id for item in payload]
    result = await db.execute(select(Modulo).where(Modulo.id.in_(ids)))
    modulos = {m.id: m for m in result.scalars().all()}
    for item in payload:
        if item.id in modulos:
            modulos[item.id].ordem = item.ordem
    await db.commit()


@router.patch("/modulos/{modulo_id}", response_model=ModuloRead)
async def atualizar_modulo(
    modulo_id: int,
    payload: ModuloUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_MODULO_EDITAR)),
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
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_MODULO_EXCLUIR)),
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
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_UNIDADE_CRIAR)),
):
    unidade = Unidade(**payload.model_dump())
    db.add(unidade)
    await db.commit()
    await db.refresh(unidade)
    return unidade


@router.patch("/unidades/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reordenar_unidades(
    payload: list[ReorderItem],
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_UNIDADE_EDITAR)),
):
    ids = [item.id for item in payload]
    result = await db.execute(select(Unidade).where(Unidade.id.in_(ids)))
    unidades = {u.id: u for u in result.scalars().all()}
    for item in payload:
        if item.id in unidades:
            unidades[item.id].ordem = item.ordem
    await db.commit()


@router.patch("/unidades/{unidade_id}", response_model=UnidadeRead)
async def atualizar_unidade(
    unidade_id: int,
    payload: UnidadeUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_UNIDADE_EDITAR)),
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
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_UNIDADE_EXCLUIR)),
):
    result = await db.execute(select(Unidade).where(Unidade.id == unidade_id))
    unidade = result.scalar_one_or_none()
    if not unidade:
        raise HTTPException(status_code=404, detail="Unidade nao encontrada")
    await db.delete(unidade)
    await db.commit()


# --- Aulas Síncronas ---


async def _aula_read_para(
    db: AsyncSession,
    aula: AulaSincrona,
    usuario_id: uuid.UUID,
) -> AulaSincronaRead:
    """Monta AulaSincronaRead expondo codigo_acesso apenas para quem pode editar a aula (issue 25)."""
    pode_editar = await _user_has_permission(db, usuario_id, Permissoes.CURSO_AULA_EDITAR)
    return AulaSincronaRead(
        **AulaSincronaRead.model_validate(aula).model_dump(exclude={"exige_codigo", "codigo_acesso"}),
        exige_codigo=bool(aula.codigo_acesso),
        codigo_acesso=aula.codigo_acesso if pode_editar else None,
    )


@router.get("/{curso_id}/aulas", response_model=list[AulaSincronaRead])
async def listar_aulas(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(AulaSincrona).where(AulaSincrona.curso_id == curso_id).order_by(AulaSincrona.data_hora)
    )
    aulas = result.scalars().all()
    return [await _aula_read_para(db, a, current_user.id) for a in aulas]


@router.post("/{curso_id}/aulas", response_model=AulaSincronaRead, status_code=status.HTTP_201_CREATED)
async def criar_aula(
    curso_id: int,
    payload: AulaSincronaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CURSO_AULA_CRIAR)),
):
    data = payload.model_dump(exclude={"criar_reuniao_teams"})
    if not data.get("codigo_acesso"):
        data["codigo_acesso"] = _gerar_codigo_acesso()
    if not data.get("data_hora_fim") and data.get("duracao_minutos"):
        data["data_hora_fim"] = data["data_hora"] + timedelta(minutes=data["duracao_minutos"])
    aula = AulaSincrona(**data, criado_por=current_user.id)
    if payload.criar_reuniao_teams:
        if not teams_service._is_configured():
            raise HTTPException(
                status_code=422,
                detail="Integracao Teams nao configurada neste ambiente. "
                "Defina TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET e "
                "TEAMS_ORGANIZER_EMAIL antes de criar reunioes.",
            )
        reuniao = await teams_service.criar_reuniao(
            titulo=aula.titulo,
            data_hora=aula.data_hora,
            duracao_minutos=aula.duracao_minutos or 60,
        )
        if reuniao:
            aula.teams_meeting_id = reuniao.get("meeting_id")
            aula.link_externo = reuniao.get("join_url")
    db.add(aula)
    await db.commit()
    await db.refresh(aula)

    from app.services.notificacoes import notificar_inscritos

    await notificar_inscritos(
        db,
        curso_id=curso_id,
        tipo="aula_agendada",
        titulo=f"Aula agendada: {aula.titulo}",
        corpo=f"Novo encontro em {aula.data_hora.strftime('%d/%m/%Y %H:%M')}.",
        referencia_tipo="aula",
        referencia_id=aula.id,
    )
    await db.commit()
    return await _aula_read_para(db, aula, current_user.id)


@router.get("/aulas/proximas", response_model=list[AulaSincronaRead])
async def aulas_proximas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    from datetime import datetime, timezone

    inscricoes = select(Inscricao.curso_id).where(Inscricao.usuario_id == current_user.id)
    result = await db.execute(
        select(AulaSincrona)
        .where(
            AulaSincrona.data_hora >= datetime.now(timezone.utc),
            AulaSincrona.curso_id.in_(inscricoes),
        )
        .order_by(AulaSincrona.data_hora)
        .limit(20)
    )
    aulas = result.scalars().all()
    return [await _aula_read_para(db, a, current_user.id) for a in aulas]


@router.patch("/aulas/{aula_id}", response_model=AulaSincronaRead)
async def atualizar_aula(
    aula_id: int,
    payload: AulaSincronaUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_AULA_EDITAR)),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")
    data = payload.model_dump(exclude_unset=True)
    if "duracao_minutos" in data and "data_hora_fim" not in data:
        inicio = data.get("data_hora") or aula.data_hora
        data["data_hora_fim"] = inicio + timedelta(minutes=data["duracao_minutos"])
    for field, value in data.items():
        setattr(aula, field, value)
    await db.commit()
    await db.refresh(aula)
    return await _aula_read_para(db, aula, current_user.id)


@router.delete("/aulas/{aula_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_aula(
    aula_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_AULA_EXCLUIR)),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")
    await db.delete(aula)
    await db.commit()


# --- Chat SSE ---


@router.get("/{curso_id}/chat/stream")
async def stream_chat(
    curso_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    from fastapi.responses import StreamingResponse

    last_id = 0

    async def event_generator():
        nonlocal last_id
        while True:
            if await request.is_disconnected():
                break
            result = await db.execute(
                select(MensagemCurso)
                .where(MensagemCurso.curso_id == curso_id, MensagemCurso.id > last_id)
                .order_by(MensagemCurso.criado_em)
            )
            novas = result.scalars().all()
            for msg in novas:
                last_id = msg.id
                data = {
                    "id": msg.id,
                    "usuario_id": str(msg.usuario_id),
                    "texto": msg.texto,
                    "criado_em": msg.criado_em.isoformat(),
                }
                yield f"data: {json.dumps(data)}\n\n"
            import asyncio

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Chat ---


@router.get("/{curso_id}/chat", response_model=list[dict])
async def listar_chat(
    curso_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    from app.models.curso import MensagemCurso

    result = await db.execute(
        select(MensagemCurso)
        .where(MensagemCurso.curso_id == curso_id)
        .order_by(MensagemCurso.criado_em.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    msgs = result.scalars().all()
    msgs.reverse()
    return [
        {"id": m.id, "usuario_id": str(m.usuario_id), "texto": m.texto, "criado_em": m.criado_em.isoformat()}
        for m in msgs
    ]


@router.post("/{curso_id}/chat", status_code=status.HTTP_201_CREATED)
async def enviar_mensagem(
    curso_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CHAT_ENVIAR)),
):
    from app.models.curso import MensagemCurso

    texto = payload.get("texto", "").strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Texto nao pode ser vazio")
    if len(texto) > 2000:
        raise HTTPException(status_code=422, detail="Texto muito longo (max 2000)")
    msg = MensagemCurso(curso_id=curso_id, usuario_id=current_user.id, texto=texto)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return {"id": msg.id, "usuario_id": str(msg.usuario_id), "texto": msg.texto, "criado_em": msg.criado_em.isoformat()}


async def _user_has_permission(db: AsyncSession, usuario_id: uuid.UUID, permissao: str) -> bool:
    from sqlalchemy.orm import selectinload

    from app.models.usuario import UsuarioPerfil

    result = await db.execute(
        select(UsuarioPerfil).where(UsuarioPerfil.usuario_id == usuario_id).options(selectinload(UsuarioPerfil.perfil))
    )
    ups = result.scalars().all()
    for up in ups:
        if up.perfil and up.perfil.permissoes and permissao in up.perfil.permissoes:
            return True
    return False


# --- Inscricoes ---


@router.post("/inscricoes", response_model=InscricaoRead, status_code=status.HTTP_201_CREATED)
async def inscrever(
    payload: InscricaoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CURSO_INSCREVER)),
):
    usuario_id = payload.usuario_id or current_user.id
    if usuario_id != current_user.id:
        has_outros = await _user_has_permission(db, current_user.id, Permissoes.CURSO_INSCREVER_OUTROS)
        if not has_outros:
            raise HTTPException(status_code=403, detail="Sem permissao para inscrever outros usuarios")

    curso = await db.execute(select(Curso).where(Curso.id == payload.curso_id))
    curso = curso.scalar_one_or_none()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")

    existente = await db.execute(
        select(Inscricao).where(
            Inscricao.usuario_id == usuario_id,
            Inscricao.curso_id == payload.curso_id,
        )
    )
    if existente.scalars().first():
        raise HTTPException(status_code=409, detail="Usuario ja inscrito neste curso")

    if curso.pre_requisito_curso_id:
        prereq = await db.execute(
            select(Inscricao).where(
                Inscricao.curso_id == curso.pre_requisito_curso_id,
                Inscricao.usuario_id == usuario_id,
                Inscricao.status == "concluido",
            )
        )
        if not prereq.scalars().first():
            raise HTTPException(status_code=403, detail="Pre-requisito nao concluido")

    inscricao = Inscricao(usuario_id=usuario_id, curso_id=payload.curso_id)
    db.add(inscricao)
    await db.commit()
    await db.refresh(inscricao)
    return inscricao


@router.get("/inscricoes/minhas", response_model=list[InscricaoRead])
async def listar_minhas_inscricoes(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CURSO_INSCREVER)),
):
    result = await db.execute(
        select(Inscricao).where(Inscricao.usuario_id == current_user.id).order_by(Inscricao.data_inscricao.desc())
    )
    return result.scalars().all()


@router.get("/inscricoes/{usuario_id}", response_model=list[InscricaoRead])
async def listar_inscricoes_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_VER_INSCRICOES)),
):
    result = await db.execute(
        select(Inscricao).where(Inscricao.usuario_id == usuario_id).order_by(Inscricao.data_inscricao.desc())
    )
    return result.scalars().all()


@router.delete("/inscricoes/{inscricao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancelar_inscricao(
    inscricao_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CURSO_INSCREVER)),
):
    result = await db.execute(select(Inscricao).where(Inscricao.id == inscricao_id))
    inscricao = result.scalar_one_or_none()
    if not inscricao:
        raise HTTPException(status_code=404, detail="Inscricao nao encontrada")
    if inscricao.usuario_id != current_user.id:
        has_outros = await _user_has_permission(db, current_user.id, Permissoes.CURSO_INSCREVER_OUTROS)
        if not has_outros:
            raise HTTPException(status_code=403, detail="Sem permissao para cancelar inscricao de outro usuario")
    await db.delete(inscricao)
    await db.commit()


# --- Progresso ---


@router.post("/unidades/{unidade_id}/concluir", response_model=ProgressoUnidadeRead)
async def concluir_unidade(
    unidade_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CURSO_INSCREVER)),
):
    try:
        progresso = await progresso_service.concluir_unidade(
            db,
            usuario_id=current_user.id,
            unidade_id=unidade_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await gamificacao_xp(db, usuario_id=current_user.id, evento="unidade_concluida", referencia_id=unidade_id)

    await db.commit()
    await db.refresh(progresso)
    return progresso


@router.post("/progresso", response_model=ProgressoUnidadeRead, status_code=status.HTTP_201_CREATED)
async def criar_progresso(
    payload: ProgressoUnidadeCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_PROGRESSO_GERENCIAR)),
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
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_PROGRESSO_GERENCIAR)),
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


@router.get("/{curso_id}/consumo")
async def consumo_curso(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CURSO_INSCREVER)),
):
    curso = await db.execute(select(Curso).where(Curso.id == curso_id))
    curso = curso.scalar_one_or_none()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso nao encontrado")

    modulos = await db.execute(select(Modulo).where(Modulo.curso_id == curso_id).order_by(Modulo.ordem))
    modulos = modulos.scalars().all()

    unidades = await db.execute(
        select(Unidade).where(Unidade.modulo_id.in_([m.id for m in modulos])).order_by(Unidade.ordem)
    )
    unidades_list = unidades.scalars().all()

    unidade_ids = [u.id for u in unidades_list]

    conteudos = await db.execute(select(Conteudo).where(Conteudo.unidade_id.in_(unidade_ids)).order_by(Conteudo.ordem))
    conteudos_list = conteudos.scalars().all()

    progressos = await db.execute(
        select(ProgressoUnidade).where(
            ProgressoUnidade.usuario_id == current_user.id,
            ProgressoUnidade.unidade_id.in_(unidade_ids),
        )
    )
    progressos_map = {p.unidade_id: p for p in progressos.scalars().all()}

    entregas = await db.execute(
        select(EntregaAtividade).where(
            EntregaAtividade.usuario_id == current_user.id,
            EntregaAtividade.unidade_id.in_(unidade_ids),
        )
    )
    entregas_list = entregas.scalars().all()

    modulos_data = []
    for m in modulos:
        unids = [u for u in unidades_list if u.modulo_id == m.id]
        unidades_data = []
        concluidas_no_modulo = 0
        for u in unids:
            cts = [c for c in conteudos_list if c.unidade_id == u.id]
            progresso = progressos_map.get(u.id)
            if progresso and progresso.status == "concluido":
                concluidas_no_modulo += 1
            entrega = [e for e in entregas_list if e.unidade_id == u.id]
            unidades_data.append(
                {
                    "id": u.id,
                    "titulo": u.titulo,
                    "tipo": u.tipo,
                    "ordem": u.ordem,
                    "conteudo_url": u.conteudo_url,
                    "url_externa": u.url_externa,
                    "conteudos": [
                        {"id": c.id, "tipo_midia": c.tipo_midia, "titulo": c.titulo, "url_arquivo": resolve_file_url(c.url_arquivo)}
                        for c in cts
                    ],
                    "progresso": {
                        "status": progresso.status if progresso else "nao_iniciado",
                        "concluido_em": progresso.concluido_em.isoformat()
                        if progresso and progresso.concluido_em
                        else None,
                    },
                    "entrega": {
                        "id": entrega[0].id,
                        "status": entrega[0].status,
                        "nota": float(entrega[0].nota) if entrega and entrega[0].nota else None,
                        "feedback": entrega[0].feedback if entrega else None,
                    }
                    if entrega
                    else None,
                }
            )
        total_no_modulo = len(unids)
        modulos_data.append(
            {
                "id": m.id,
                "titulo": m.titulo,
                "ordem": m.ordem,
                "total_unidades": total_no_modulo,
                "unidades_concluidas": concluidas_no_modulo,
                "progresso_pct": round((concluidas_no_modulo / total_no_modulo * 100), 2) if total_no_modulo else 0,
                "unidades": unidades_data,
            }
        )

    return {
        "id": curso.id,
        "titulo": curso.titulo,
        "descricao": curso.descricao,
        "modulos": modulos_data,
    }


@router.get("/{curso_id}/progresso/{usuario_id}")
async def progresso_usuario_curso(
    curso_id: int,
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CURSO_VER_INSCRICOES)),
):
    curso = await db.execute(select(Curso).where(Curso.id == curso_id))
    if not curso.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Curso nao encontrado")
    return await progresso_service.progresso_curso_detalhado(db, usuario_id=usuario_id, curso_id=curso_id)


async def _processar_gravacao_lazy(db: AsyncSession, aula: AulaSincrona) -> dict | None:
    """Dispara a gravacao automaticamente se a aula ja terminou e ainda nao gravou.

    Idempotente: nao faz nada se ja existir gravacao, se nao houver reuniao Teams
    vinculada, ou se a aula ainda nao terminou. Falhas sao silenciosas (retry
    natural no proximo acesso).
    """
    if aula.gravacao_conteudo_id is not None:
        return None
    if not aula.teams_meeting_id:
        return None

    if aula.data_hora_fim and aula.data_hora_fim > datetime.now(timezone.utc):
        return None

    resultado = await teams_service.processar_gravacao(
        meeting_id=aula.teams_meeting_id,
        titulo_aula=aula.titulo,
        db_session=db,
    )
    if resultado.get("success"):
        aula.gravacao_conteudo_id = resultado.get("conteudo_id")
        await db.commit()
        from app.services.notificacoes import notificar_inscritos

        await notificar_inscritos(
            db,
            curso_id=aula.curso_id,
            tipo="gravacao_disponivel",
            titulo=f"Gravacao disponivel: {aula.titulo}",
            corpo="A gravacao desta aula ja esta disponivel.",
            referencia_tipo="aula",
            referencia_id=aula.id,
        )
        await db.commit()
    return resultado


@router.post("/aulas/{aula_id}/processar-gravacao", response_model=ProcessarGravacaoResponse)
async def processar_gravacao_aula(
    aula_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AULA_PROCESSAR_GRAVACAO)),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")
    if not aula.teams_meeting_id:
        raise HTTPException(status_code=400, detail="Aula nao possui reuniao Teams vinculada")

    resultado = await teams_service.processar_gravacao(
        meeting_id=aula.teams_meeting_id,
        titulo_aula=aula.titulo,
        db_session=db,
    )

    if resultado["success"]:
        aula.gravacao_conteudo_id = resultado["conteudo_id"]
        await db.commit()

    return resultado


@router.get("/aulas/{aula_id}/presenca", response_model=list[PresencaRegistroRead])
async def listar_presenca_aula(
    aula_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.AULA_VER_PRESENCA)),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")
    if not aula.teams_meeting_id:
        raise HTTPException(status_code=400, detail="Aula nao possui reuniao Teams vinculada")

    return await teams_service.sincronizar_presenca(
        meeting_id=aula.teams_meeting_id,
        aula_id=aula.id,
    )


@router.post("/aulas/{aula_id}/acessar", response_model=AcessarAulaResponse)
async def acessar_aula(
    aula_id: int,
    payload: AcessarAulaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    if aula.codigo_acesso and payload.codigo_acesso != aula.codigo_acesso:
        raise HTTPException(status_code=403, detail="Codigo de acesso invalido")

    inscrito = await db.execute(
        select(Inscricao).where(Inscricao.curso_id == aula.curso_id, Inscricao.usuario_id == current_user.id)
    )
    if not inscrito.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Usuario nao esta inscrito no curso")

    await _processar_gravacao_lazy(db, aula)

    return AcessarAulaResponse(
        aula_id=aula.id,
        titulo=aula.titulo,
        link_externo=aula.link_externo,
        data_hora=aula.data_hora,
        data_hora_fim=aula.data_hora_fim,
    )


@router.post("/aulas/{aula_id}/entrar", response_model=PresencaAulaRead, status_code=status.HTTP_201_CREATED)
async def entrar_aula(
    aula_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    inscrito = await db.execute(
        select(Inscricao).where(Inscricao.curso_id == aula.curso_id, Inscricao.usuario_id == current_user.id)
    )
    if not inscrito.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Usuario nao esta inscrito no curso")

    # evita duplicar entrada aberta (chamar entrar 2x = 1 linha)
    aberta = await db.execute(
        select(PresencaAula).where(
            PresencaAula.aula_id == aula_id,
            PresencaAula.usuario_id == current_user.id,
            PresencaAula.hora_saida.is_(None),
        )
    )
    if aberta.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Entrada ja registrada nesta aula")

    xff = request.headers.get("x-forwarded-for", "")
    ip_acesso = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)

    presenca = PresencaAula(
        aula_id=aula.id,
        usuario_id=current_user.id,
        hora_entrada=datetime.now(timezone.utc),
        ip_acesso=ip_acesso,
    )
    db.add(presenca)
    await db.commit()
    await db.refresh(presenca)
    await _broadcast_presenca(aula_id, "entrou", current_user)
    return presenca


@router.post("/aulas/{aula_id}/sair", response_model=PresencaAulaRead)
async def sair_aula(
    aula_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    presenca_result = await db.execute(
        select(PresencaAula)
        .where(
            PresencaAula.aula_id == aula_id,
            PresencaAula.usuario_id == current_user.id,
            PresencaAula.hora_saida.is_(None),
        )
        .order_by(PresencaAula.hora_entrada.desc())
    )
    presenca = presenca_result.scalars().first()
    if not presenca:
        raise HTTPException(status_code=404, detail="Entrada nao encontrada para esta aula")

    agora = datetime.now(timezone.utc)
    presenca.hora_saida = agora
    presenca.tempo_permanencia_seg = max(0, int((agora - presenca.hora_entrada).total_seconds()))
    presenca.presente = presenca.tempo_permanencia_seg >= 60
    await db.commit()
    await db.refresh(presenca)
    await _broadcast_presenca(aula_id, "saiu", current_user)
    return presenca


async def _fechar_presencas_lazy(db: AsyncSession, aula: AulaSincrona) -> None:
    """Fecha automaticamente presencas abertas de uma aula ja encerrada.

    Quando a aula ja terminou (data_hora_fim no passado), presencas sem
    hora_saida sao fechadas com hora_saida = data_hora_fim e tempo de
    permanencia calculado. Idempotente: presencas ja fechadas nao sao
    alteradas. Lazy: dispara apenas ao consultar/relatar (sem cron).
    """
    if not aula.data_hora_fim or aula.data_hora_fim > datetime.now(timezone.utc):
        return

    result = await db.execute(
        select(PresencaAula).where(
            PresencaAula.aula_id == aula.id,
            PresencaAula.hora_saida.is_(None),
        )
    )
    presencas = result.scalars().all()
    MIN_PERMANENCIA_SEG = 60
    for presenca in presencas:
        presenca.hora_saida = aula.data_hora_fim
        presenca.tempo_permanencia_seg = max(
            0, int((aula.data_hora_fim - presenca.hora_entrada).total_seconds())
        )
        presenca.saida_estimada = True
        presenca.presente = presenca.tempo_permanencia_seg >= MIN_PERMANENCIA_SEG
    if presencas:
        await db.commit()


@router.get("/aulas/{aula_id}/presencas", response_model=list[PresencaAulaRead])
async def listar_presencas_aula(
    aula_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AULA_VER_PRESENCA)),
):
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    await _fechar_presencas_lazy(db, aula)

    result = await db.execute(
        select(PresencaAula).where(PresencaAula.aula_id == aula_id).order_by(PresencaAula.hora_entrada)
    )
    return result.scalars().all()


@router.get("/aulas/minhas-presencas", response_model=list[PresencaAulaRead])
async def minhas_presencas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Presencas do participante logado (issue 25, ponto 8) — sem permissao admin."""
    result = await db.execute(
        select(PresencaAula)
        .where(PresencaAula.usuario_id == current_user.id)
        .order_by(PresencaAula.hora_entrada.desc())
    )
    return result.scalars().all()


@router.get("/aulas/presencas", response_model=dict)
async def consultar_presencas_admin(
    curso_id: int | None = Query(None, description="Filtra por curso"),
    usuario_id: uuid.UUID | None = Query(None, description="Filtra por participante"),
    de: datetime | None = Query(None, description="Inicio do periodo (ISO)"),
    ate: datetime | None = Query(None, description="Fim do periodo (ISO)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.AULA_VER_PRESENCA)),
):
    """Consulta administrativa de presencas (TI2-94).

    Filtros: curso, participante e periodo (de/ate). Retorna itens paginados
    (X-Total-Count) + resumo agregado do resultado filtrado.
    """
    query = select(PresencaAula)
    if curso_id is not None:
        query = query.join(AulaSincrona, AulaSincrona.id == PresencaAula.aula_id).where(
            AulaSincrona.curso_id == curso_id
        )
    if usuario_id is not None:
        query = query.where(PresencaAula.usuario_id == usuario_id)
    if de is not None:
        query = query.where(PresencaAula.hora_entrada >= de)
    if ate is not None:
        query = query.where(PresencaAula.hora_entrada <= ate)

    total = await count_query(db, query)
    rows = (await db.execute(query.order_by(PresencaAula.hora_entrada.desc()).offset(skip).limit(limit))).scalars().all()

    aula_ids = {p.aula_id for p in rows}
    aulas = {}
    if aula_ids:
        aulas_res = await db.execute(select(AulaSincrona).where(AulaSincrona.id.in_(aula_ids)))
        aulas = {a.id: a for a in aulas_res.scalars().all()}

    curso_ids = {a.curso_id for a in aulas.values()}
    cursos = {}
    if curso_ids:
        cursos_res = await db.execute(select(Curso).where(Curso.id.in_(curso_ids)))
        cursos = {c.id: c for c in cursos_res.scalars().all()}

    user_ids = {p.usuario_id for p in rows}
    usuarios = {}
    if user_ids:
        us_res = await db.execute(select(Usuario).where(Usuario.id.in_(user_ids)))
        usuarios = {u.id: u for u in us_res.scalars().all()}

    itens = [
        PresencaConsultaItem(
            id=p.id,
            aula_id=p.aula_id,
            aula_titulo=aulas[p.aula_id].titulo if p.aula_id in aulas else "",
            curso_id=aulas[p.aula_id].curso_id if p.aula_id in aulas else None,
            curso_titulo=cursos[aulas[p.aula_id].curso_id].titulo
            if p.aula_id in aulas and aulas[p.aula_id].curso_id in cursos
            else "",
            usuario_id=p.usuario_id,
            usuario_nome=usuarios[p.usuario_id].nome_completo if p.usuario_id in usuarios else "",
            email=usuarios[p.usuario_id].email if p.usuario_id in usuarios else "",
            hora_entrada=p.hora_entrada,
            hora_saida=p.hora_saida,
            tempo_permanencia_seg=p.tempo_permanencia_seg,
            presente=p.presente,
            saida_estimada=p.saida_estimada,
        )
        for p in rows
    ]

    todas = (await db.execute(query.order_by(PresencaAula.hora_entrada))).scalars().all()
    tempos = [p.tempo_permanencia_seg or 0 for p in todas]
    resumo = PresencaResumoRead(
        total_presencas=len(todas),
        total_presentes=sum(1 for p in todas if p.presente),
        media_tempo_seg=round(sum(tempos) / len(tempos), 2) if tempos else 0.0,
        tempo_total_seg=sum(tempos),
    )

    response.headers["X-Total-Count"] = str(total)
    return {"itens": itens, "resumo": resumo}


@router.get("/aulas/{aula_id}/presencas/relatorio")
async def relatorio_presencas_aula(
    aula_id: int,
    formato: str = Query("csv", pattern="^(csv|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AULA_VER_PRESENCA)),
):
    """Relatorio de presencas da aula em CSV (TI2-93).

    Fecha presencas em aberto (lazy) antes de gerar, para o relatorio refletir
    a situacao final da aula.
    """
    result = await db.execute(select(AulaSincrona).where(AulaSincrona.id == aula_id))
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    await _fechar_presencas_lazy(db, aula)

    presencas = (
        await db.execute(
            select(PresencaAula).where(PresencaAula.aula_id == aula_id).order_by(PresencaAula.hora_entrada)
        )
    ).scalars().all()

    usuarios_ids = {p.usuario_id for p in presencas}
    usuarios = {}
    if usuarios_ids:
        rows = await db.execute(select(Usuario).where(Usuario.id.in_(usuarios_ids)))
        usuarios = {u.id: u for u in rows.scalars().all()}

    if formato == "pdf":
        return await _relatorio_presencas_pdf(aula, presencas, usuarios)

    return _relatorio_presencas_csv(aula, presencas, usuarios)


def _relatorio_presencas_csv(
    aula: AulaSincrona,
    presencas: list[PresencaAula],
    usuarios: dict,
) -> Response:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Relatorio de presenca - Aula", aula.titulo])
    writer.writerow(["Data", aula.data_hora.strftime("%d/%m/%Y %H:%M")])
    writer.writerow([])
    writer.writerow(["Participante", "Email", "Entrada", "Saida", "Tempo (min)", "Presente", "Saida estimada"])

    for p in presencas:
        usuario = usuarios.get(p.usuario_id)
        nome = usuario.nome_completo if usuario else "Desconhecido"
        email = usuario.email if usuario else ""
        tempo = (p.tempo_permanencia_seg or 0) // 60
        writer.writerow(
            [
                nome,
                email,
                p.hora_entrada.strftime("%d/%m/%Y %H:%M"),
                p.hora_saida.strftime("%d/%m/%Y %H:%M") if p.hora_saida else "em aberto",
                tempo,
                "Sim" if p.presente else "Nao",
                "Sim" if p.saida_estimada else "Nao",
            ]
        )

    filename = f"presencas_aula_{aula.id}.csv"
    return Response(
        content=b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _relatorio_presencas_pdf(
    aula: AulaSincrona,
    presencas: list[PresencaAula],
    usuarios: dict,
) -> Response:
    """Relatorio PDF de presenca (TI2-93, parte 2) via reportlab."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Presencas - {aula.titulo}")
    styles = getSampleStyleSheet()

    elementos = [
        Paragraph(f"Relatorio de presenca - Aula: {aula.titulo}", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Data: {aula.data_hora.strftime('%d/%m/%Y %H:%M')}", styles["Normal"]),
        Spacer(1, 12),
    ]

    cabecalho = ["Participante", "Email", "Entrada", "Saida", "Tempo (min)", "Presente", "Saida estimada"]
    linhas = [cabecalho]
    for p in presencas:
        usuario = usuarios.get(p.usuario_id)
        nome = usuario.nome_completo if usuario else "Desconhecido"
        email = usuario.email if usuario else ""
        tempo = (p.tempo_permanencia_seg or 0) // 60
        linhas.append(
            [
                nome,
                email,
                p.hora_entrada.strftime("%d/%m/%Y %H:%M"),
                p.hora_saida.strftime("%d/%m/%Y %H:%M") if p.hora_saida else "em aberto",
                tempo,
                "Sim" if p.presente else "Nao",
                "Sim" if p.saida_estimada else "Nao",
            ]
        )

    tabela = Table(linhas)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EAF1F8")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elementos.append(tabela)

    doc.build(elementos)
    buffer.seek(0)
    filename = f"presencas_aula_{aula.id}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Chat em tempo real da aula (US-13) ---

# Issue 25 (P11): conexoes em memoria do processo — broadcast alcanca apenas
# o worker local. Em dev (1 worker) funciona; com replicas, migrar para um
# pub/sub (ex: Redis) antes de subir em producao.
_ws_connections: dict[int, set[WebSocket]] = {}
_presentes_por_ws: dict[int, dict[str, str]] = {}  # aula_id -> {usuario_id: nome}


async def _broadcast_presenca(aula_id: int, acao: str, usuario: Usuario) -> None:
    """Avisa quem esta no socket da aula que alguem entrou ou saiu (issue 27)."""
    payload = {
        "type": "presenca",
        "acao": acao,  # "entrou" | "saiu"
        "usuario_id": str(usuario.id),
        "usuario_nome": usuario.nome_completo,
    }
    for conn in list(_ws_connections.get(aula_id, ())):
        try:
            await conn.send_json(payload)
        except Exception:
            _ws_connections.get(aula_id, set()).discard(conn)


@router.websocket("/aulas/{aula_id}/chat/ws")
async def chat_aula_websocket(websocket: WebSocket, aula_id: int):
    """WebSocket de chat em tempo real da aula (US-13, T-13.1).

    Autentica via token JWT no subprotocolo (recomendado, nao vaza em log)
    ou na query string (?token=...) como fallback, valida que a aula existe
    e faz broadcast das mensagens para todos os conectados na aula.
    """
    from app.services.auth import decode_token

    token = None
    if websocket.headers.get("sec-websocket-protocol"):
        token = websocket.headers["sec-websocket-protocol"].split(",")[0].strip()
    if not token:
        token = websocket.query_params.get("token")

    payload = decode_token(token or "")
    if not payload or not payload.get("sub"):
        await websocket.close(code=4401)
        return

    try:
        async with async_session() as db:
            aula = await db.get(AulaSincrona, aula_id)
            if not aula:
                await websocket.close(code=4404)
                return
            usuario_id = uuid.UUID(payload["sub"])
            usuario = await db.get(Usuario, usuario_id)
            if not usuario:
                await websocket.close(code=4401)
                return
            await websocket.accept()
            connections = _ws_connections.setdefault(aula_id, set())
            connections.add(websocket)
            presentes = _presentes_por_ws.setdefault(aula_id, {})
            presentes[str(usuario_id)] = usuario.nome_completo or ""
            await websocket.send_json(
                {
                    "type": "presenca_inicial",
                    "presentes": [
                        {"usuario_id": uid, "usuario_nome": nome}
                        for uid, nome in presentes.items()
                    ],
                }
            )
            try:
                while True:
                    data = await websocket.receive_json()
                    agora = datetime.now(timezone.utc)
                    from app.models.usuario import UsuarioAulaSilenciado

                    sil_registro = await db.execute(
                        select(UsuarioAulaSilenciado).where(
                            UsuarioAulaSilenciado.usuario_id == usuario_id,
                            UsuarioAulaSilenciado.aula_id == aula_id,
                        )
                    )
                    sil_por_aula = sil_registro.scalar_one_or_none()
                    silenciado_ate = sil_por_aula.silenciado_ate if sil_por_aula else None
                    if silenciado_ate and silenciado_ate > agora:
                        await websocket.send_json(
                            {
                                "type": "erro",
                                "detail": "Voce esta silenciado no chat ate "
                                + silenciado_ate.isoformat(),
                            }
                        )
                        continue
                    texto = (data.get("texto") or "").strip()
                    if not texto or len(texto) > 2000:
                        await websocket.send_json({"type": "erro", "detail": "Texto invalido (max 2000)"})
                        continue
                    msg = MensagemAula(
                        aula_id=aula_id,
                        usuario_id=usuario.id,
                        texto=texto,
                    )
                    db.add(msg)
                    await db.commit()
                    await db.refresh(msg)
                    payload_out = {
                        "type": "mensagem",
                        "id": msg.id,
                        "aula_id": msg.aula_id,
                        "usuario_id": str(msg.usuario_id),
                        "usuario_nome": usuario.nome_completo,
                        "texto": msg.texto,
                        "criado_em": msg.criado_em.isoformat(),
                    }
                    for conn in list(connections):
                        try:
                            await conn.send_json(payload_out)
                        except Exception:
                            connections.discard(conn)
            except WebSocketDisconnect:
                pass
            finally:
                connections.discard(websocket)
                presentes.pop(str(usuario_id), None)
    except Exception:
        try:
            await websocket.close(code=4500)
        except Exception:
            pass


@router.get("/aulas/{aula_id}/chat", response_model=list[MensagemAulaRead])
async def listar_chat_aula(
    aula_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CHAT_VISUALIZAR)),
):
    aula = await db.get(AulaSincrona, aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    result = await db.execute(
        select(MensagemAula)
        .where(MensagemAula.aula_id == aula_id, MensagemAula.excluida.is_(False))
        .order_by(MensagemAula.criado_em.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    msgs = result.scalars().all()
    msgs.reverse()

    usuarios_ids = {m.usuario_id for m in msgs}
    usuarios = {}
    if usuarios_ids:
        rows = await db.execute(select(Usuario).where(Usuario.id.in_(usuarios_ids)))
        usuarios = {u.id: u.nome_completo for u in rows.scalars().all()}

    return [
        MensagemAulaRead(
            id=m.id,
            aula_id=m.aula_id,
            usuario_id=str(m.usuario_id),
            usuario_nome=usuarios.get(m.usuario_id, ""),
            texto=m.texto,
            excluida=m.excluida,
            criado_em=m.criado_em,
        )
        for m in msgs
    ]


@router.post("/aulas/{aula_id}/chat", response_model=MensagemAulaRead, status_code=status.HTTP_201_CREATED)
async def enviar_mensagem_aula(
    aula_id: int,
    payload: MensagemAulaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CHAT_ENVIAR)),
):
    aula = await db.get(AulaSincrona, aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    agora = datetime.now(timezone.utc)
    from app.models.usuario import UsuarioAulaSilenciado

    sil_registro = await db.execute(
        select(UsuarioAulaSilenciado).where(
            UsuarioAulaSilenciado.usuario_id == current_user.id,
            UsuarioAulaSilenciado.aula_id == aula_id,
        )
    )
    sil_por_aula = sil_registro.scalar_one_or_none()
    if sil_por_aula and sil_por_aula.silenciado_ate and sil_por_aula.silenciado_ate > agora:
        raise HTTPException(
            status_code=403,
            detail=f"Usuario silenciado no chat ate {sil_por_aula.silenciado_ate.isoformat()}",
        )

    texto = payload.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Texto nao pode ser vazio")
    if len(texto) > 2000:
        raise HTTPException(status_code=422, detail="Texto muito longo (max 2000)")

    msg = MensagemAula(aula_id=aula_id, usuario_id=current_user.id, texto=texto)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return MensagemAulaRead(
        id=msg.id,
        aula_id=msg.aula_id,
        usuario_id=str(msg.usuario_id),
        usuario_nome=current_user.nome_completo,
        texto=msg.texto,
        excluida=msg.excluida,
        criado_em=msg.criado_em,
    )


# --- Moderacao do chat da aula (US-13, T-13.4) ---


@router.delete("/aulas/{aula_id}/chat/{mensagem_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_mensagem_aula(
    aula_id: int,
    mensagem_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CHAT_MODERAR)),
):
    """Exclui (logicamente) uma mensagem do chat da aula. Apenas moderadores."""
    aula = await db.get(AulaSincrona, aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    result = await db.execute(
        select(MensagemAula).where(MensagemAula.id == mensagem_id, MensagemAula.aula_id == aula_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")

    msg.excluida = True
    await db.commit()


@router.patch("/aulas/{aula_id}/chat/silenciar/{usuario_id}", response_model=dict)
async def silenciar_usuario_chat(
    aula_id: int,
    usuario_id: uuid.UUID,
    silenciado_ate: datetime | None = Query(None, description="ISO; null ou ausente = silenciar por 24h"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CHAT_MODERAR)),
):
    """Silencia um usuario no chat. Sem silenciado_ate, silencia por 24h."""
    aula = await db.get(AulaSincrona, aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada")

    usuario = await db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    from app.models.usuario import UsuarioAulaSilenciado

    ate = silenciado_ate or datetime.now(timezone.utc) + timedelta(hours=24)
    existente = await db.execute(
        select(UsuarioAulaSilenciado).where(
            UsuarioAulaSilenciado.usuario_id == usuario_id,
            UsuarioAulaSilenciado.aula_id == aula_id,
        )
    )
    registro = existente.scalar_one_or_none()
    if registro:
        registro.silenciado_ate = ate
    else:
        db.add(UsuarioAulaSilenciado(usuario_id=usuario_id, aula_id=aula_id, silenciado_ate=ate))
    await db.commit()
    return {"usuario_id": str(usuario.id), "aula_id": aula_id, "silenciado_ate": ate.isoformat()}
