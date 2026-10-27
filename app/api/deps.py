import uuid

from fastapi import Depends, HTTPException, Request, status
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
from app.services.lgpd import aceite_pendente, rota_liberada
from app.services.rbac import has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.ROOT_PATH.rstrip('/')}/api/v1/auth/login")


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """Resolve o usuario do token e aplica o bloqueio de LGPD (issue #119).

    O bloqueio fica aqui, num ponto so, e nao numa dependencia por rota:
    require_credenciamento nao e usada por rota nenhuma e 47 rotas dependem
    de get_current_user direto, entao qualquer outro lugar deixaria parte da
    API aberta. Nasce desligado (LGPD_BLOQUEIO_ATIVO).
    """
    user = await _resolver_usuario(token, db)
    if (
        settings.LGPD_BLOQUEIO_ATIVO
        and aceite_pendente(user.aceite_lgpd, user.versao_termo_lgpd)
        and not rota_liberada(request.url.path)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aceite do termo de uso e da politica de privacidade pendente.",
        )
    return user


async def _resolver_usuario(token: str, db: AsyncSession) -> Usuario:
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
                # Issue #122 item 2: so liga a conta se o e-mail do token
                # estiver verificado. Sem isso, quem conseguisse um token do
                # realm declarando o e-mail de outra pessoa assumia a conta
                # dela - e os perfis dela. Claim ausente conta como nao
                # verificada: `is True` e deliberado, nao `truthy`.
                #
                # A recusa fica AQUI, e nao na entrada do `if email`: la, pular
                # o vinculo fazia o fluxo seguir para o provisionamento logo
                # abaixo, que tentava criar outro usuario com o mesmo e-mail e
                # estourava a unicidade - 500 em vez de 401.
                if (
                    settings.KEYCLOAK_EXIGIR_EMAIL_VERIFICADO
                    and kc_payload.get("email_verified") is not True
                ):
                    raise credentials_exception
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
            # Issue #119: nascia True, ou seja, a plataforma registrava um
            # consentimento que a pessoa nunca deu - era o segundo relato da
            # Tatiana. Quem chega pelo Keycloak (inclusive gov.br) nasce sem
            # aceite e aceita pela rota POST /usuarios/me/aceite-lgpd.
            aceite_lgpd=False,
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
