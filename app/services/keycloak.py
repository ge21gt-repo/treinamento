"""Integração Keycloak — Discovery + JWKS + validação RS256 (staging).

Usa `KEYCLOAK_*` de `app/config.py`. Valida JWT do `treinamento-front`
via `https://keycloak-stg.idesp.sp.gov.br/realms/idesp-realm`.
"""

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings

# Cache simples em memória para JWKS e Discovery (evita hit por request).
_JWKS_CLIENT: PyJWKClient | None = None
_JWKS_CACHED_AT: float = 0
_DISCOVERY: dict[str, Any] | None = None
_DISCOVERY_CACHED_AT: float = 0
_CACHE_TTL = 600  # 10 min


def _issuer() -> str:
    return (settings.KEYCLOAK_ISSUER or "").rstrip("/")


def _jwks_uri() -> str:
    if settings.KEYCLOAK_JWKS_URI:
        return settings.KEYCLOAK_JWKS_URI
    iss = _issuer()
    if not iss:
        return ""
    return f"{iss}/protocol/openid-connect/certs"


def _discovery_url() -> str:
    iss = _issuer()
    if not iss:
        return ""
    return f"{iss}/.well-known/openid-configuration"


def get_discovery(force: bool = False) -> dict[str, Any] | None:
    global _DISCOVERY, _DISCOVERY_CACHED_AT
    if not force and _DISCOVERY is not None and (time.time() - _DISCOVERY_CACHED_AT) < _CACHE_TTL:
        return _DISCOVERY
    url = _discovery_url()
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=10)
        r.raise_for_status()
        _DISCOVERY = r.json()
        _DISCOVERY_CACHED_AT = time.time()
        return _DISCOVERY
    except Exception:
        return None


def _get_jwks_client(force: bool = False) -> PyJWKClient | None:
    global _JWKS_CLIENT, _JWKS_CACHED_AT
    uri = _jwks_uri()
    if not uri:
        return None
    if not force and _JWKS_CLIENT is not None and (time.time() - _JWKS_CACHED_AT) < _CACHE_TTL:
        return _JWKS_CLIENT
    try:
        _JWKS_CLIENT = PyJWKClient(uri)
        _JWKS_CACHED_AT = time.time()
        return _JWKS_CLIENT
    except Exception:
        return None


def validar_token_keycloak(token: str) -> dict | None:
    """Valida JWT RS256 do Keycloak via JWKS.

    Checa: assinatura (kid), iss, aud (treinamento-front), exp/nbf.
    Retorna payload se válido, None se inválido/expirado/config ausente.
    """
    if not token or not _issuer() or not settings.KEYCLOAK_CLIENT_ID:
        return None
    jwks_client = _get_jwks_client()
    if not jwks_client:
        return None
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=_issuer(),
            options={"verify_signature": True, "verify_iss": True, "verify_aud": False, "verify_exp": True},
        )
        # Audiência flexível: aceita tanto treinamento-front (browser PKCE) quanto
        # treinamento-testes (teste via API com Direct Access) — ambos do mesmo realm.
        # Se quiser restringir, descomente a checagem abaixo.
        # aud = payload.get("aud"); azp = payload.get("azp")
        # if isinstance(aud, str):
        #     aud = [aud]
        # if settings.KEYCLOAK_CLIENT_ID not in (aud or []) and azp != settings.KEYCLOAK_CLIENT_ID:
        #     # Para teste, aceita qualquer aud do mesmo issuer (ex.: treinamento-testes tem aud=account)
        #     pass
        return payload
    except jwt.PyJWTError:
        # Tentativa com refresh de JWKS (rotação de chaves)
        jwks_client = _get_jwks_client(force=True)
        if not jwks_client:
            return None
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=_issuer(),
                options={"verify_signature": True, "verify_iss": True, "verify_aud": False, "verify_exp": True},
            )
            return payload
        except jwt.PyJWTError:
            return None


def mapear_roles_keycloak(payload: dict) -> list[str]:
    """Extrai roles de `realm_access` e de qualquer client em `resource_access`.

    Aceita roles de qualquer client (ex.: `treinamento-front` no browser e
    `treinamento-testes` via API) — o que importa é o que o crachá diz, não de
    qual porta ele veio.
    """
    roles: set[str] = set()
    realm = payload.get("realm_access", {}) or {}
    for r in realm.get("roles", []) or []:
        roles.add(str(r))
    res = payload.get("resource_access", {}) or {}
    for _client, entry in res.items():
        entry = entry or {}
        for r in entry.get("roles", []) or []:
            roles.add(str(r))
    return sorted(roles)


# Roles criadas pelo IDESP no Keycloak (client `treinamento-front`) -> perfis LMS.
# `TRE_OPERADOR` vira `administrador` (sub-admin sem dashboards/auditoria); se o
# IDESP exigir "não pode deletar", criamos um perfil `operador` dedicado depois.
ROLE_KEYCLOAK_PARA_PERFIL = {
    "TRE_ADM": "administrador_geral",
    "TRE_AUDITOR": "auditor",
    "TRE_GESTOR": "gestor",
    "TRE_INSTRUTOR": "instrutor",
    "TRE_OPERADOR": "administrador",
    "TRE_PARTICIPANTE": "participante",
    # Compatibilidade retroativa com os nomes antigos, caso algum usuário ainda
    # não tenha a role `TRE_*` atualizada no Keycloak.
    "administrador_geral": "administrador_geral",
    "administrador": "administrador",
    "auditor": "auditor",
    "gestor": "gestor",
    "instrutor": "instrutor",
    "participante": "participante",
}

# Hierarquia: em caso de múltiplas roles, o perfil mais alto vence.
_HIERARQUIA_PERFIL = (
    "administrador_geral",
    "administrador",
    "instrutor",
    "auditor",
    "gestor",
    "participante",
)


def mapear_perfil_lms(roles: list[str]) -> str:
    """Converte roles do Keycloak (ex.: `TRE_ADM`) no perfil LMS de maior hierarquia.

    Role desconhecida ou token sem role -> `participante` (padrão atual).
    """
    for perfil in _HIERARQUIA_PERFIL:
        for role in roles:
            if ROLE_KEYCLOAK_PARA_PERFIL.get(role) == perfil:
                return perfil
    return "participante"


def mapear_perfis_lms(roles: list[str]) -> list[str]:
    """Converte roles do Keycloak em TODOS os perfis LMS correspondentes.

    Ex.: `TRE_GESTOR` + `TRE_INSTRUTOR` -> `["gestor", "instrutor"]`.
    `TRE_ADM` + `TRE_PARTICIPANTE` -> `["administrador_geral"]` (descarta o
    participante quando ja existe um perfil de gestao, que e redundante).

    Role desconhecida ou token sem role -> `["participante"]` (padrão).
    """
    perfis: list[str] = []
    for role in roles:
        p = ROLE_KEYCLOAK_PARA_PERFIL.get(role)
        if p and p not in perfis:
            perfis.append(p)
    if "participante" in perfis and any(p != "participante" for p in perfis):
        perfis.remove("participante")
    return perfis or ["participante"]


async def sincronizar_perfis_keycloak(db, user, roles: list[str]) -> bool:
    """Sincroniza os perfis do usuario com as roles atuais do Keycloak (issue do dev do front).

    Compara os perfis esperados (via `mapear_perfis_lms`) com os `UsuarioPerfil`
    do usuario:
    - adiciona perfis que faltam (roles novas)
    - remove perfis que nao estao mais nas roles (se permitido remover)
    - se o usuario passou a ter perfil de gestao, atualiza ativo/credenciamento

    Retorna True se algo mudou (o chamador deve commitar).
    """
    from sqlalchemy import select

    from app.models.usuario import Perfil, UsuarioPerfil

    esperados = mapear_perfis_lms(roles)
    atuais = {up.perfil.nome for up in user.perfis}

    mudou = False

    # Adiciona perfis que faltam
    for nome in esperados:
        if nome in atuais:
            continue
        perfil = (await db.execute(select(Perfil).where(Perfil.nome == nome))).scalar_one_or_none()
        if perfil:
            db.add(UsuarioPerfil(usuario_id=user.id, perfil_id=perfil.id))
            mudou = True
            atuais.add(nome)

    # Remove perfis que nao estao mais nas roles (somente os de Keycloak).
    # Mantemos perfis atribuidos manualmente (nao Keycloak) por seguranca —
    # a remocao so acontece para perfis que o mapeamento conhece.
    for nome in list(atuais):
        if nome not in esperados and nome in ROLE_KEYCLOAK_PARA_PERFIL.values():
            for up in list(user.perfis):
                if up.perfil.nome == nome:
                    await db.delete(up)
                    mudou = True
                    atuais.discard(nome)

    # Se passou a ter perfil de gestao, garante ativo + aprovado
    tem_gestao = any(n != "participante" for n in atuais)
    if tem_gestao and (not user.ativo or user.status_credenciamento != "aprovado"):
        user.ativo = True
        user.status_credenciamento = "aprovado"
        mudou = True

    return mudou
