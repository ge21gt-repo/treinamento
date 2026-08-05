import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import check_unique_fields
from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.credenciamento import AprovacaoHierarquica, SolicitacaoCredenciamento
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.services.paginacao import apply_search, count_query
from app.services.rbac import Permissoes, can_create_perfil
from app.schemas.usuario import (
    CriarSubordinadoRequest,
    PerfilCreate,
    PerfilRead,
    PerfilUpdate,
    UsuarioPerfilCreate,
    UsuarioRead,
    UsuarioUpdate,
)
from app.services.auth import hash_password

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/me", response_model=UsuarioRead)
async def me(current_user: Usuario = Depends(get_current_user)):
    return current_user


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    perfil_nome: str | None = Query(None, description="Filtrar por nome do perfil"),
    q: str | None = Query(None, description="Busca textual por nome ou email"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_LISTAR)),
):
    query = select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))

    if perfil_nome:
        query = (
            query.join(UsuarioPerfil, Usuario.id == UsuarioPerfil.usuario_id)
            .join(Perfil)
            .where(Perfil.nome == perfil_nome)
        )

    query = apply_search(query, [Usuario.nome_completo, Usuario.email], q)
    total = await count_query(db, query)

    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()

    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/{usuario_id}", response_model=UsuarioRead)
async def obter_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_LISTAR)),
):
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == usuario_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    return user


@router.patch("/{usuario_id}", response_model=UsuarioRead)
async def atualizar_usuario(
    usuario_id: uuid.UUID,
    payload: UsuarioUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_EDITAR)),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == usuario_id)
    )
    return result.scalar_one()


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_EXCLUIR)),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    await db.delete(user)
    await db.commit()


# --- Perfis ---


@router.get("/perfis/todos", response_model=list[PerfilRead])
async def listar_perfis(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_LISTAR)),
):
    result = await db.execute(select(Perfil))
    return result.scalars().all()


@router.post("/perfis", response_model=PerfilRead, status_code=status.HTTP_201_CREATED)
async def criar_perfil(
    payload: PerfilCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_CRIAR)),
):
    perfil = Perfil(**payload.model_dump())
    db.add(perfil)
    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.post("/perfis/atribuir", status_code=status.HTTP_201_CREATED)
async def atribuir_perfil(
    payload: UsuarioPerfilCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_ATRIBUIR)),
    current_user: Usuario = Depends(get_current_user),
):
    up = UsuarioPerfil(
        usuario_id=payload.usuario_id,
        perfil_id=payload.perfil_id,
        atribuido_por=current_user.id,
    )
    db.add(up)
    await db.commit()
    return {"detail": "Perfil atribuido com sucesso"}


@router.patch("/perfis/{perfil_id}", response_model=PerfilRead)
async def atualizar_perfil(
    perfil_id: int,
    payload: PerfilUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_EDITAR)),
):
    result = await db.execute(select(Perfil).where(Perfil.id == perfil_id))
    perfil = result.scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(perfil, field, value)
    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.delete("/perfis/{perfil_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_perfil(
    perfil_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_EXCLUIR)),
):
    result = await db.execute(select(Perfil).where(Perfil.id == perfil_id))
    perfil = result.scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")
    # Nao permitir excluir perfil com usuarios vinculados
    count_result = await db.execute(
        select(func.count()).select_from(UsuarioPerfil).where(UsuarioPerfil.perfil_id == perfil_id)
    )
    if count_result.scalar_one() > 0:
        raise HTTPException(
            status_code=409, detail="Perfil possui usuarios vinculados. Remova os vinculos antes de excluir."
        )
    await db.delete(perfil)
    await db.commit()


@router.post("/criar-subordinado", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def criar_subordinado(
    payload: CriarSubordinadoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    _: None = Depends(require_permissao(Permissoes.USUARIO_CRIAR)),
):
    """Endpoint para gestor criar conta de subordinado com perfil definido"""
    # Verificar se o perfil solicitado existe no banco
    perfil_existente = await db.execute(select(Perfil).where(Perfil.nome == payload.perfil))
    perfil = perfil_existente.scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=400, detail=f"Perfil '{payload.perfil}' não encontrado")

    # Validar hierarquia: quem cria pode criar este perfil?
    perfis_criador = [up.perfil.nome for up in current_user.perfis] if current_user.perfis else []
    autorizado = any(can_create_perfil(p, payload.perfil) for p in perfis_criador)
    if not autorizado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Seu perfil não tem permissão para criar usuários do perfil '{payload.perfil}'",
        )

    # Validar aceite LGPD
    if not payload.aceite_lgpd:
        raise HTTPException(status_code=422, detail="Aceite dos termos LGPD é obrigatorio")

    # Verificar unicidade de email, CPF e telefone
    await check_unique_fields(db, payload.email, payload.cpf, payload.telefone)

    # Criar usuario subordinado
    subordinado = Usuario(
        nome_completo=payload.nome_completo,
        email=payload.email,
        cpf=payload.cpf,
        senha_hash=hash_password(payload.senha),
        orgao_instituicao=payload.orgao_instituicao,
        cargo=payload.cargo,
        telefone=payload.telefone,
        ativo=True,
        status_credenciamento="aprovado",
        criado_por=current_user.id,
        aceite_lgpd=True,
        data_aceite_lgpd=datetime.now(timezone.utc),
    )
    db.add(subordinado)
    await db.flush()

    # Atribuir perfil solicitado
    db.add(UsuarioPerfil(usuario_id=subordinado.id, perfil_id=perfil.id, atribuido_por=current_user.id))

    # Criar solicitacao de credenciamento como aprovada (trilha de auditoria)
    solicitacao = SolicitacaoCredenciamento(
        usuario_id=subordinado.id,
        perfil_solicitado=payload.perfil,
        status="aprovado",
        avaliado_por=current_user.id,
        avaliado_em=datetime.now(timezone.utc),
    )
    db.add(solicitacao)
    await db.flush()

    # Registrar aprovacao hierarquica
    perfis_criador = [up.perfil.nome for up in current_user.perfis] if current_user.perfis else []
    nivel_hierarquico = perfis_criador[0] if perfis_criador else "participante"
    db.add(AprovacaoHierarquica(
        solicitacao_id=solicitacao.id,
        aprovador_id=current_user.id,
        nivel_hierarquico=nivel_hierarquico,
        acao="aprovar",
        motivo="Criado por superior hierarquico",
    ))

    await db.commit()
    await db.refresh(subordinado)
    # Carregar perfis para o schema UsuarioRead
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == subordinado.id)
    )
    return result.scalar_one()
