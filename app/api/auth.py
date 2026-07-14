import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.rate_limit import limiter
from app.config import settings
from app.database import get_db
from app.models.token_reset import TokenResetSenha
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.schemas.usuario import (
    EsqueciSenhaRequest,
    LoginRequest,
    RedefinirSenhaRequest,
    Token,
    UsuarioCreate,
    UsuarioRead,
    UsuarioRegistro,
)
from app.services.auth import create_access_token, hash_password, verify_password
from app.services.credenciamento import criar_solicitacao_credenciamento
from app.services.email import send_reset_email

router = APIRouter(prefix="/auth", tags=["Autenticacao"])


async def check_unique_fields(db: AsyncSession, email: str, cpf: str | None, telefone: str | None):
    """Valida unicidade de email, CPF e telefone antes do cadastro."""
    existing = await db.execute(select(Usuario).where(Usuario.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email ja cadastrado")

    if cpf:
        existing = await db.execute(select(Usuario).where(Usuario.cpf == cpf))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="CPF ja cadastrado")

    if telefone:
        existing = await db.execute(select(Usuario).where(Usuario.telefone == telefone))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Telefone ja cadastrado")


@router.post("/registro", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def registrar(request: Request, payload: UsuarioCreate, db: AsyncSession = Depends(get_db)):
    if not payload.aceite_lgpd:
        raise HTTPException(status_code=422, detail="Aceite dos termos LGPD é obrigatorio")

    await check_unique_fields(db, payload.email, payload.cpf, payload.telefone)

    user = Usuario(
        nome_completo=payload.nome_completo,
        email=payload.email,
        cpf=payload.cpf,
        senha_hash=hash_password(payload.senha),
        orgao_instituicao=payload.orgao_instituicao,
        cargo=payload.cargo,
        telefone=payload.telefone,
        avatar_url=payload.avatar_url,
        aceite_lgpd=True,
        data_aceite_lgpd=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    perfil_participante = await db.execute(select(Perfil).where(Perfil.nome == "participante"))
    perfil = perfil_participante.scalar_one_or_none()
    if perfil:
        db.add(UsuarioPerfil(usuario_id=user.id, perfil_id=perfil.id))

    await db.commit()
    # Recarregar com perfis para o schema UsuarioRead
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == user.id)
    )
    return result.scalar_one()


@router.post("/registro-com-perfil", response_model=dict, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def registrar_com_perfil(request: Request, payload: UsuarioRegistro, db: AsyncSession = Depends(get_db)):
    if not payload.aceite_lgpd:
        raise HTTPException(status_code=422, detail="Aceite dos termos LGPD é obrigatorio")

    perfis_validos = ["administrador_geral", "instrutor", "gestor", "participante"]
    if payload.perfil_solicitado not in perfis_validos:
        raise HTTPException(status_code=400, detail=f"Perfil invalido. Perfis validos: {', '.join(perfis_validos)}")

    await check_unique_fields(db, payload.email, payload.cpf, payload.telefone)

    solicitacao = await criar_solicitacao_credenciamento(payload, db)

    return {
        "message": "Solicitacao de credenciamento criada com sucesso",
        "solicitacao_id": solicitacao.id,
        "usuario_id": str(solicitacao.usuario_id),
        "perfil_solicitado": solicitacao.perfil_solicitado,
        "status": solicitacao.status,
        "instrucao": "Aguarde aprovacao do gestor/admin para acesso",
    }


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.email == payload.email)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    if not user.ativo:
        raise HTTPException(status_code=403, detail="Usuario desativado")

    user.ultimo_acesso = datetime.now(timezone.utc)
    await db.commit()

    perfis = [up.perfil.nome for up in user.perfis] if user.perfis else []
    token = create_access_token({"sub": str(user.id), "perfis": perfis})
    return Token(access_token=token)


@router.post("/logout")
async def logout():
    return {"message": "Logout realizado com sucesso"}


@router.post("/esqueci-senha")
@limiter.limit("3/minute")
async def esqueci_senha(request: Request, payload: EsqueciSenhaRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    user = result.scalar_one_or_none()

    if not user:
        return {"message": "Se o email estiver cadastrado, voce recebera um link de redefinicao"}

    token_raw = secrets.token_urlsafe(32)
    token_hash = bcrypt.hash(token_raw)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES)

    reset = TokenResetSenha(
        usuario_id=user.id,
        token=token_hash,
        expira_em=expires_at,
    )
    db.add(reset)
    await db.commit()

    link_reset = f"{settings.BASE_URL}/auth/redefinir-senha?token={token_raw}"
    send_reset_email(user.email, user.nome_completo, link_reset)

    return {"message": "Se o email estiver cadastrado, voce recebera um link de redefinicao"}


@router.post("/redefinir-senha")
async def redefinir_senha(payload: RedefinirSenhaRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TokenResetSenha)
        .where(
            not TokenResetSenha.utilizado,
            TokenResetSenha.expira_em > datetime.now(timezone.utc),
        )
        .order_by(TokenResetSenha.criado_em.desc())
    )
    tokens = result.scalars().all()

    reset = None
    for t in tokens:
        if bcrypt.verify(payload.token, t.token):
            reset = t
            break

    if not reset:
        raise HTTPException(status_code=400, detail="Token invalido ou expirado")

    reset.utilizado = True

    result = await db.execute(select(Usuario).where(Usuario.id == reset.usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    user.senha_hash = hash_password(payload.nova_senha)
    await db.commit()

    return {"message": "Senha redefinida com sucesso"}
