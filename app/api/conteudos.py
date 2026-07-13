from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.conteudo import Conteudo, MaterialComplementar
from app.models.usuario import Usuario
from app.schemas.conteudo import (
    ConteudoCreate,
    ConteudoRead,
    ConteudoUpdate,
    MaterialComplementarCreate,
    MaterialComplementarRead,
    MaterialComplementarUpdate,
)
from app.services.rbac import Permissoes
from app.services.storage import upload_file, delete_file

router = APIRouter(prefix="/conteudos", tags=["Conteudos"])


@router.get("", response_model=list[ConteudoRead])
async def listar_conteudos(
    unidade_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_VISUALIZAR)),
):
    q = select(Conteudo)
    if unidade_id is not None:
        q = q.where(Conteudo.unidade_id == unidade_id)
    q = q.order_by(Conteudo.ordem).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


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
        "video": "videos", "pdf": "pdfs", "audio": "audios",
        "scorm": "scorm", "document": "documentos", "image": "imagens",
    }
    folder = folder_map.get(tipo_midia, "outros")
    url = await upload_file(arquivo, folder)
    conteudo = Conteudo(
        unidade_id=unidade_id,
        tipo_midia=tipo_midia,
        titulo=titulo,
        descricao=descricao,
        mime_type=arquivo.content_type,
        url_arquivo=url,
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
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_VISUALIZAR)),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
    return conteudo


@router.get("/{conteudo_id}/player", response_model=ConteudoRead)
async def player_conteudo(
    conteudo_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CONTEUDO_VISUALIZAR)),
):
    result = await db.execute(select(Conteudo).where(Conteudo.id == conteudo_id))
    conteudo = result.scalar_one_or_none()
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteudo nao encontrado")
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
    await delete_file(conteudo.url_arquivo)
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
    url = await upload_file(arquivo, folder)
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
    await delete_file(material.url_arquivo)
    await db.delete(material)
    await db.commit()
