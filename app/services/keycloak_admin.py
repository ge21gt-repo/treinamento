"""Cliente da Admin API do Keycloak (issue #115).

`app/services/keycloak.py` valida o token do usuário (JWKS, `iss`, roles). Este
módulo é o outro lado: administra usuários e roles no realm, usando um client
confidencial **separado** do client do front, com service account
(`client_credentials`).

Regras que valem para tudo aqui:

- configuração só por variável de ambiente (`KEYCLOAK_ADMIN_CLIENT_ID` /
  `KEYCLOAK_ADMIN_CLIENT_SECRET`), nunca no código;
- timeouts curtos;
- o corpo de erro do Keycloak **não** é repassado para a resposta nem para o
  log (pode conter detalhe interno), e o segredo nunca é logado;
- falha de qualquer chamada vira `KeycloakAdminError`, que a rota deve traduzir
  em **502** com mensagem clara.
"""

import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 10.0

# Perfil LMS -> role do client do front. É o inverso de
# `ROLE_KEYCLOAK_PARA_PERFIL` (que inclui os nomes antigos; aqui só as TRE_*).
PERFIL_PARA_ROLE_KEYCLOAK: dict[str, str] = {
    "administrador_geral": "TRE_ADM",
    "administrador": "TRE_OPERADOR",
    "gestor": "TRE_GESTOR",
    "instrutor": "TRE_INSTRUTOR",
    "auditor": "TRE_AUDITOR",
    "participante": "TRE_PARTICIPANTE",
}

ROLES_TRE = set(PERFIL_PARA_ROLE_KEYCLOAK.values())


class KeycloakAdminError(Exception):
    """Falha ao falar com a Admin API do Keycloak (a rota devolve 502)."""


_token_cache: dict[str, object] = {"valor": None, "expira_em": 0.0}
_client_uuid_cache: dict[str, str] = {}
_token_lock = asyncio.Lock()


def _resetar_cache() -> None:
    """Limpa os caches em memória (usado nos testes)."""
    _token_cache["valor"] = None
    _token_cache["expira_em"] = 0.0
    _client_uuid_cache.clear()


def _configurado() -> bool:
    return bool(
        settings.KEYCLOAK_SERVER
        and settings.KEYCLOAK_REALM
        and settings.KEYCLOAK_ADMIN_CLIENT_ID
        and settings.KEYCLOAK_ADMIN_CLIENT_SECRET
    )


def _server() -> str:
    return settings.KEYCLOAK_SERVER.rstrip("/")


def _base_url() -> str:
    return f"{_server()}/admin/realms/{settings.KEYCLOAK_REALM}"


async def _obter_token() -> str:
    """Token de serviço, cacheado até perto de expirar."""
    if not _configurado():
        raise KeycloakAdminError("Admin API do Keycloak nao configurada")

    agora = time.monotonic()
    cacheado = _token_cache["valor"]
    if cacheado and agora < float(_token_cache["expira_em"]):
        return str(cacheado)

    async with _token_lock:
        agora = time.monotonic()
        cacheado = _token_cache["valor"]
        if cacheado and agora < float(_token_cache["expira_em"]):
            return str(cacheado)

        url = f"{_server()}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
        dados = {
            "grant_type": "client_credentials",
            "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                resposta = await cliente.post(url, data=dados)
        except httpx.HTTPError as exc:
            raise KeycloakAdminError("Falha de rede ao obter token de servico") from exc

        if resposta.status_code != 200:
            raise KeycloakAdminError("Keycloak recusou as credenciais do servico")

        try:
            corpo = resposta.json()
        except ValueError as exc:
            raise KeycloakAdminError("Resposta invalida do Keycloak ao obter token") from exc

        token = corpo.get("access_token")
        if not token:
            raise KeycloakAdminError("Keycloak nao devolveu access_token")

        expires_in = int(corpo.get("expires_in") or 60)
        _token_cache["valor"] = token
        _token_cache["expira_em"] = time.monotonic() + max(5, expires_in - 30)
        return token


async def _requisitar(
    metodo: str,
    caminho: str,
    *,
    json_body=None,
    params: dict | None = None,
    esperado: tuple[int, ...] = (200,),
) -> httpx.Response:
    token = await _obter_token()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
            resposta = await cliente.request(
                metodo,
                f"{_base_url()}{caminho}",
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )
    except httpx.HTTPError as exc:
        raise KeycloakAdminError("Falha de rede na Admin API do Keycloak") from exc

    if resposta.status_code not in esperado:
        # Nunca repassar o corpo: pode conter detalhe interno do Keycloak.
        raise KeycloakAdminError(f"Keycloak respondeu {resposta.status_code} em {metodo} {caminho}")
    return resposta


async def buscar_usuario_por_email(email: str) -> dict | None:
    """Retorna o usuário do Keycloak com esse e-mail, ou None."""
    resposta = await _requisitar("GET", "/users", params={"email": email, "exact": "true"})
    usuarios = resposta.json()
    if not isinstance(usuarios, list):
        raise KeycloakAdminError("Resposta inesperada do Keycloak ao buscar usuario")
    for usuario in usuarios:
        if (usuario.get("email") or "").lower() == email.lower():
            return usuario
    return None


async def criar_usuario(email: str, nome: str, *, habilitado: bool = True) -> str:
    """Cria o usuário no Keycloak e devolve o `sub`."""
    corpo = {
        "username": email,
        "email": email,
        "firstName": nome or email,
        "enabled": habilitado,
        "emailVerified": False,
    }
    await _requisitar("POST", "/users", json_body=corpo, esperado=(201,))

    # O 201 devolve o id no header Location; buscar por e-mail é mais simples e
    # confirma que o usuário existe de fato.
    usuario = await buscar_usuario_por_email(email)
    if not usuario or not usuario.get("id"):
        raise KeycloakAdminError("Usuario criado no Keycloak nao foi encontrado")
    return usuario["id"]


async def _uuid_do_client(client_id: str | None = None) -> str:
    """UUID interno do client (a Admin API usa o id, não o clientId)."""
    alvo = client_id or settings.KEYCLOAK_CLIENT_ID
    if not alvo:
        raise KeycloakAdminError("KEYCLOAK_CLIENT_ID nao configurado")
    if alvo in _client_uuid_cache:
        return _client_uuid_cache[alvo]

    resposta = await _requisitar("GET", "/clients", params={"clientId": alvo})
    for cliente in resposta.json() or []:
        if cliente.get("clientId") == alvo and cliente.get("id"):
            _client_uuid_cache[alvo] = cliente["id"]
            return cliente["id"]
    raise KeycloakAdminError(f"Client {alvo} nao encontrado no Keycloak")


async def definir_role(sub: str, perfil: str) -> None:
    """Troca a role `TRE_*` do usuário: remove as antigas e põe a do perfil."""
    role = PERFIL_PARA_ROLE_KEYCLOAK.get(perfil)
    if not role:
        raise KeycloakAdminError(f"Perfil sem role Keycloak: {perfil}")

    uuid = await _uuid_do_client()

    resposta = await _requisitar("GET", f"/clients/{uuid}/roles")
    roles_por_nome = {item.get("name"): item for item in resposta.json() or []}
    nova = roles_por_nome.get(role)
    if not nova:
        raise KeycloakAdminError(f"Role {role} nao existe no client do treinamento")

    resposta = await _requisitar("GET", f"/users/{sub}/role-mappings/clients/{uuid}")
    atuais = [item for item in resposta.json() or [] if (item.get("name") or "") in ROLES_TRE]

    remover = [item for item in atuais if item.get("name") != role]
    if remover:
        await _requisitar(
            "DELETE",
            f"/users/{sub}/role-mappings/clients/{uuid}",
            json_body=remover,
            esperado=(204,),
        )

    if not any(item.get("name") == role for item in atuais):
        await _requisitar(
            "POST",
            f"/users/{sub}/role-mappings/clients/{uuid}",
            json_body=[{"id": nova["id"], "name": role}],
            esperado=(204,),
        )


async def definir_habilitado(sub: str, habilitado: bool) -> None:
    """Ativa/desativa o usuário no Keycloak (`enabled`)."""
    await _requisitar(
        "PUT",
        f"/users/{sub}",
        json_body={"enabled": habilitado},
        esperado=(204,),
    )


async def enviar_email_de_acao(sub: str, acoes: list[str] | None = None) -> None:
    """Pede ao Keycloak para enviar e-mail de ação (definir senha/verificar)."""
    lista = acoes or ["UPDATE_PASSWORD", "VERIFY_EMAIL"]
    await _requisitar(
        "PUT",
        f"/users/{sub}/execute-actions-email",
        json_body=lista,
        esperado=(204,),
    )
