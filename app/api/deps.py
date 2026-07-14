import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.services.auth import decode_token
from app.services.rbac import has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.ativo:
        raise credentials_exception
    return user


async def require_credenciamento(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    """Dependency para verificar se usuario esta credenciado (aprovado)"""
    if current_user.status_credenciamento != "aprovado":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuario não credenciado. Aguarde aprovacao do gestor/admin."
        )
    return current_user


def require_permissao(permissao: str):
    """Factory que retorna uma dependency para verificar permissão específica"""

    async def _check_permissao(
        current_user: Usuario = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Usuario:
        if current_user.status_credenciamento != "aprovado":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario não credenciado. Aguarde aprovacao do gestor/admin.",
            )

        result = await db.execute(select(Perfil).join(UsuarioPerfil).where(UsuarioPerfil.usuario_id == current_user.id))
        perfil = result.scalar_one_or_none()

        if not perfil:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario não tem perfil atribuído.")

        if not has_permission(perfil.nome, permissao):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Perfil '{perfil.nome}' não tem permissão '{permissao}'."
            )

        return current_user

    return _check_permissao
