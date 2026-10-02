import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.credenciamento import SolicitacaoCredenciamento
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.services.auth import decode_token
from app.services.keycloak import (
    mapear_perfis_lms,
    mapear_roles_keycloak,
    sincronizar_perfis_keycloak,
    validar_token_keycloak,
)
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

    # 1) Tentar Keycloak (RS256 via JWKS) — staging idesp-realm
    kc_payload = validar_token_keycloak(token)
    if kc_payload is not None:
        sub = kc_payload.get("sub")
        email = kc_payload.get("email") or kc_payload.get("preferred_username") or kc_payload.get("upn")
        if not sub:
            raise credentials_exception
        # Busca por keycloak_sub
        result = await db.execute(
            select(Usuario)
            .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
            .where(Usuario.keycloak_sub == str(sub))
        )
        user = result.scalar_one_or_none()
        if user:
            if not user.ativo:
                raise credentials_exception
            # Sincroniza roles/perfis a cada login (issue do dev do front):
            # se o Wagner mudar a role no Keycloak, o perfil acompanha.
            roles = mapear_roles_keycloak(kc_payload)
            if await sincronizar_perfis_keycloak(db, user, roles):
                await db.commit()
            # Recarrega os perfis (o sync insere/remove UsuarioPerfil sem tocar
            # na colecao em memoria) para o /usuarios/me devolver o estado novo.
            result = await db.execute(
                select(Usuario)
                .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
                .where(Usuario.id == user.id)
                .execution_options(populate_existing=True)
            )
            user = result.scalar_one()
            return user
        # Fallback por email (vincula conta existente)
        if email:
            result = await db.execute(
                select(Usuario)
                .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
                .where(Usuario.email == str(email).lower())
            )
            user = result.scalar_one_or_none()
            if user:
                user.keycloak_sub = str(sub)
                user.auth_provider = "keycloak"
                # Sincroniza os perfis ja neste ramo: quem e ligado por e-mail
                # na primeira requisicao recebe os perfis das roles atuais de
                # imediato, sem esperar a proxima requisicao (issue #95 ponto 4).
                roles = mapear_roles_keycloak(kc_payload)
                if await sincronizar_perfis_keycloak(db, user, roles):
                    await db.commit()
                # Recarrega os perfis para devolver o estado sincronizado.
                result = await db.execute(
                    select(Usuario)
                    .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
                    .where(Usuario.id == user.id)
                    .execution_options(populate_existing=True)
                )
                user = result.scalar_one()
                if not user.ativo:
                    raise credentials_exception
                return user
        # Provisionamento: cria usuário vinculado ao Keycloak
        nome = kc_payload.get("name") or kc_payload.get("given_name") or email or f"keycloak-{sub[:8]}"
        # Mapear roles Keycloak -> perfil local (se não mapear, usa participante).
        # Entende as roles do IDESP (TRE_ADM, TRE_GESTOR, ...) e os nomes antigos.
        roles = mapear_roles_keycloak(kc_payload)
        perfis = mapear_perfis_lms(roles)
        perfil_nome = perfis[0]
        # Perfis de gestao (role dada pelo IDESP) nascem aprovados direto;
        # participante nasce APROVADO por padrao (KEYCLOAK_PARTICIPANTE_APROVADO),
        # mantendo a opcao reversivel de nascer pendente + solicitacao (fluxo antigo).
        participante_aprovado = settings.KEYCLOAK_PARTICIPANTE_APROVADO
        perfil_gestao = perfil_nome != "participante"
        aprovado_direto = perfil_gestao or participante_aprovado
        user = Usuario(
            nome_completo=str(nome)[:200],
            email=str(email).lower() if email else f"{sub}@keycloak.local",
            senha_hash=None,
            ativo=aprovado_direto,
            status_credenciamento="aprovado" if aprovado_direto else "pendente",
            aceite_lgpd=True,
            keycloak_sub=str(sub),
            auth_provider="keycloak",
        )
        db.add(user)
        await db.flush()
        # Cria um UsuarioPerfil para cada role (varias roles -> varios perfis).
        for p_nome in perfis:
            result = await db.execute(select(Perfil).where(Perfil.nome == p_nome))
            perfil = result.scalar_one_or_none()
            if perfil:
                db.add(UsuarioPerfil(usuario_id=user.id, perfil_id=perfil.id))
        if not aprovado_direto:
            # Participante pendente: cria solicitacao para o admin aprovar (fluxo local).
            db.add(
                SolicitacaoCredenciamento(
                    usuario_id=user.id,
                    perfil_solicitado=perfil_nome,
                    status="pendente",
                )
            )
        await db.commit()
        # Recarregar com perfis
        result = await db.execute(
            select(Usuario)
            .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
            .where(Usuario.id == user.id)
        )
        user = result.scalar_one()
        return user

    # 2) Fallback: JWT interno (HS256)
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    result = await db.execute(
        select(Usuario)
        .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
        .where(Usuario.id == uuid.UUID(user_id))
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
        perfis = result.scalars().all()

        if not perfis:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario não tem perfil atribuído.")

        if not any(has_permission(p.nome, permissao) for p in perfis):
            nomes = ", ".join(p.nome for p in perfis)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Nenhum dos perfis '{nomes}' tem permissão '{permissao}'.",
            )

        return current_user

    return _check_permissao
