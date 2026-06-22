from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.schemas.usuario import LoginRequest, Token, UsuarioCreate, UsuarioRead
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Autenticacao"])


@router.post("/registro", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def registrar(payload: UsuarioCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email ja cadastrado")

    user = Usuario(
        nome_completo=payload.nome_completo,
        email=payload.email,
        cpf=payload.cpf,
        senha_hash=hash_password(payload.senha),
        orgao_instituicao=payload.orgao_instituicao,
        cargo=payload.cargo,
        telefone=payload.telefone,
        avatar_url=payload.avatar_url,
    )
    db.add(user)
    await db.flush()

    perfil_participante = await db.execute(select(Perfil).where(Perfil.nome == "participante"))
    perfil = perfil_participante.scalar_one_or_none()
    if perfil:
        db.add(UsuarioPerfil(usuario_id=user.id, perfil_id=perfil.id))

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    if not user.ativo:
        raise HTTPException(status_code=403, detail="Usuario desativado")

    user.ultimo_acesso = datetime.now(timezone.utc)
    await db.commit()

    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)
