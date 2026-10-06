from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissao
from app.database import get_db
from app.models.conteudo import Conteudo, MaterialComplementar
from app.models.curso import Curso, Modulo, Unidade
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.services.paginacao import apply_search, count_query
from app.schemas.conteudo import (
    ConteudoCreate,
    ConteudoRead,
    ConteudoUpdate,
    IniciarUploadChunkedRequest,
    IniciarUploadChunkedResponse,
    MaterialComplementarCreate,
    MaterialComplementarRead,
    MaterialComplementarUpdate,
    UploadChunkedStatusResponse,
)
from app.services.chunked_upload import ChunkedUploadTracker
from app.services.rbac import Permissoes, has_permission
from app.services.storage import delete_file, upload_file

router = APIRouter(prefix="/conteudos", tags=["Conteudos"])


async def _pode_gerenciar_conteudo(db: AsyncSession, usuario: Usuario) -> bool:
    """Quem tem permissao de criar conteudo ve tambem curso rascunho (issue #102)."""
    perfis = (
        await db.execute(
            select(Perfil).join(UsuarioPerfil).where(UsuarioPerfil.usuario_id == usuario.id)
        )
    ).scalars().all()
    return any(has_permission(p.nome, Permissoes.CONTEUDO_CRIAR) for p in perfis)


async def _curso_do_conteudo(db: AsyncSession, conteudo: Conteudo) -> Curso | None:
    if conteudo.unidade_id is None:
        return None
    return (
        await db.execute(
            select(Curso)
            .join(Modulo, Modulo.curso_id == Curso.id)
            .join(Unidade, Unidade.modulo_id == Modulo.id)
            .where(Unidade.id == conteudo.unidade_id)
        )
    ).scalar_one_or_none()


async def _conteudo_visivel(db: AsyncSession, conteudo: Conteudo, usuario: Usuario) -> None:
    """404 se o conteudo for de curso ainda nao publicado e o usuario nao o gerencia."""
    curso = await _curso_do_conteudo(db, conteudo)
    if curso is not None and not curso.publicado:
        if not await _pode_gerenciar_conteudo(db, usuario):
            raise HTTPException(status_code=404, detail="Conteudo nao encontrado")


def _conteudo_read(conteudo: Conteudo, curso: Curso | None, unidade: Unidade | None) -> ConteudoRead:
    read = ConteudoRead.model_validate(conteudo)
    read.curso_id = curso.id if curso else None
    read.curso_titulo = curso.titulo if curso else None
    read.unidade_titulo = unidade.titulo if unidade else None
    return read


@router.get("", response_model=list[ConteudoRead])
async def listar_conteudos(
    unidade_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, description="Busca textual por titulo ou descricao"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    current_user: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_VISUALIZAR)),
):
    query = (
        select(Conteudo, Curso, Unidade)
        .outerjoin(Unidade, Unidade.id == Conteudo.unidade_id)
        .outerjoin(Modulo, Modulo.id == Unidade.modulo_id)
        .outerjoin(Curso, Curso.id == Modulo.curso_id)
    )
    if unidade_id is not None:
        query = query.where(Conteudo.unidade_id == unidade_id)
    query = apply_search(query, [Conteudo.titulo, Conteudo.descricao], q)
    # Issue #102: quem nao gerencia conteudo so ve material de curso publicado.
    if not await _pode_gerenciar_conteudo(db, current_user):
        query = query.where(or_(Conteudo.unidade_id.is_(None), Curso.publicado.is_(True)))
    total = await count_query(db, query)
    result = await db.execute(query.order_by(Conteudo.ordem).offset(skip).limit(limit))
    response.headers["X-Total-Count"] = str(total)
    return [_conteudo_read(c, curso, unidade) for (c, curso, unidade) in result.all()]


@router.post("", response_model=ConteudoRead, status_code=status.HTTP_201_CREATED)
async def criar_conteudo(
    payload: ConteudoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_CRIAR)),
):
    conteudo = Conteudo(**payload.model_dump(), criado_por=current_user.id)
    db.add(conteudo)
    await db.commit()
    await db.refresh(conteudo)
    return conteudo


@router.post("/upload", response_model=ConteudoRead, status_code=status.HTTP_201_CREATED)
async def upload_conteudo(
    unidade_id: int = Query(...),
    tipo_midia: str = Query(...),
    titulo: str = Query(...),
    descricao: str | None = Query(None),
    duracao_segundos: int | None = Query(None),
    ordem: int = Query(0),
    arquivo: UploadFile = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_CRIAR)),
):
    folder_map = {
        "video": "videos",
        "pdf": "pdfs",
        "audio": "audios",
        "scorm": "scorm",
        "document": "documentos",
        "image": "imagens",
    }
    folder = folder_map.get(tipo_midia, "outros")
    try:
        url, tamanho = await upload_file(arquivo, folder)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    conteudo = Conteudo(
        unidade_id=unidade_id,
        tipo_midia=tipo_midia,
        titulo=titulo,
        descricao=descricao,
        mime_type=arquivo.content_type,
        url_arquivo=url,
        tamanho_bytes=tamanho,
        duracao_segundos=duracao_segundos,
        ordem=ordem,
        criado_por=current_user.id,
    )
    db.add(conteudo)
    await db.commit()
    await db.refresh(conteudo)
    return conteudo


# --- Chunked Upload (Retomável) ---


@router.post("/upload/iniciar", response_model=IniciarUploadChunkedResponse)
async def iniciar_upload_chunked(
    payload: IniciarUploadChunkedRequest,
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_CRIAR)),
):
    upload_id = ChunkedUploadTracker.init_upload(
        filename=payload.filename,
        folder=payload.folder,
        total_chunks=payload.total_chunks,
    )
    return IniciarUploadChunkedResponse(
        upload_id=upload_id,
        filename=payload.filename,
        folder=payload.folder,
        total_chunks=payload.total_chunks,
    )


@router.post("/upload/{upload_id}/chunk", status_code=status.HTTP_204_NO_CONTENT)
async def upload_chunk(
    upload_id: str,
    chunk_index: int = Query(...),
    request: Request = None,
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_CRIAR)),
):
    data = await request.body()
    try:
        ChunkedUploadTracker.save_chunk(upload_id, chunk_index, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/upload/{upload_id}/status", response_model=UploadChunkedStatusResponse)
async def status_upload_chunked(
    upload_id: str,
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_CRIAR)),
):
    try:
        meta = ChunkedUploadTracker.get_status(upload_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    missing = ChunkedUploadTracker.list_missing(upload_id)
    return UploadChunkedStatusResponse(
        upload_id=upload_id,
        total_chunks=meta["total_chunks"],
        received_chunks=meta["received_chunks"],
        missing_chunks=missing,
        complete=len(missing) == 0,
    )


@router.post("/upload/{upload_id}/completar", response_model=ConteudoRead, status_code=status.HTTP_201_CREATED)
async def completar_upload_chunked(
    upload_id: str,
    unidade_id: int = Query(...),
    tipo_midia: str = Query(...),
    titulo: str = Query(...),
    descricao: str | None = Query(None),
    duracao_segundos: int | None = Query(None),
    ordem: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_CRIAR)),
):
    try:
        url, tamanho = ChunkedUploadTracker.complete_and_store(upload_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    conteudo = Conteudo(
        unidade_id=unidade_id,
        tipo_midia=tipo_midia,
        titulo=titulo,
        descricao=descricao,
        url_arquivo=url,
        tamanho_bytes=tamanho,
        duracao_segundos=duracao_segundos,
        ordem=ordem,
        criado_por=current_user.id,
    )
    db.add(conteudo)
    await db.commit()
    await db.refresh(conteudo)
    return conteudo


@router.get("/{conteudo_id}", response_model=ConteudoRead)
async def obter_conteudo(
    conteudo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_VISUALIZAR)),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    await _conteudo_visivel(db, conteudo, current_user)
    return conteudo


@router.get("/{conteudo_id}/player", response_model=ConteudoRead)
async def player_conteudo(
    conteudo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_VISUALIZAR)),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    await _conteudo_visivel(db, conteudo, current_user)
    return conteudo


@router.patch("/{conteudo_id}", response_model=ConteudoRead)
async def atualizar_conteudo(
    conteudo_id: int,
    payload: ConteudoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_EDITAR)),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(conteudo, field, value)
    await db.commit()
    await db.refresh(conteudo)
    return conteudo


@router.delete("/{conteudo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_conteudo(
    conteudo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_EXCLUIR)),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    try:
        await delete_file(conteudo.url_arquivo)
    except Exception:
        pass
    await db.delete(conteudo)
    await db.commit()


# --- Materiais Complementares ---


@router.get("/materiais/{curso_id}", response_model=list[MaterialComplementarRead])
async def listar_materiais(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_VISUALIZAR)),
):
    result = await db.execute(select(MaterialComplementar).where(MaterialComplementar.curso_id == curso_id))
    return result.scalars().all()


@router.post("/materiais", response_model=MaterialComplementarRead, status_code=status.HTTP_201_CREATED)
async def criar_material(
    payload: MaterialComplementarCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.MATERIAL_GERENCIAR)),
):
    material = MaterialComplementar(**payload.model_dump(), criado_por=current_user.id)
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material


@router.post("/materiais/upload", response_model=MaterialComplementarRead, status_code=status.HTTP_201_CREATED)
async def upload_material(
    curso_id: int = Query(...),
    titulo: str = Query(...),
    tipo: str = Query(...),
    arquivo: UploadFile = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.MATERIAL_GERENCIAR)),
):
    folder_map = {"pdf": "pdfs", "document": "documentos", "video": "videos", "audio": "audios", "image": "imagens"}
    folder = folder_map.get(tipo, "complementares")
    try:
        url, _tamanho = await upload_file(arquivo, folder)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    material = MaterialComplementar(
        curso_id=curso_id,
        titulo=titulo,
        tipo=tipo,
        mime_type=arquivo.content_type,
        url_arquivo=url,
        criado_por=current_user.id,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material


@router.patch("/materiais/{material_id}", response_model=MaterialComplementarRead)
async def atualizar_material(
    material_id: int,
    payload: MaterialComplementarUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.MATERIAL_GERENCIAR)),
):
    result = await db.execute(select(MaterialComplementar).where(MaterialComplementar.id == material_id))
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="Material nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(material, field, value)
    await db.commit()
    await db.refresh(material)
    return material


@router.delete("/materiais/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_material(
    material_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.MATERIAL_GERENCIAR)),
):
    result = await db.execute(select(MaterialComplementar).where(MaterialComplementar.id == material_id))
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="Material nao encontrado")
    try:
        await delete_file(material.url_arquivo)
    except Exception:
        pass
    await db.delete(material)
    await db.commit()
