import time
import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings


def _gen_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem, public_pem


def _make_token(private_pem, payload_overrides=None, kid="test-kid"):
    payload = {
        "iss": settings.KEYCLOAK_ISSUER,
        "aud": settings.KEYCLOAK_CLIENT_ID,
        "sub": "kc-test-sub-001",
        "email": "kc.test@test.com",
        "name": "KC Test",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
        "realm_access": {"roles": ["participante"]},
        "resource_access": {settings.KEYCLOAK_CLIENT_ID: {"roles": ["participante"]}},
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


def test_validar_token_keycloak_ok():
    private_pem, public_pem = _gen_keypair()
    token = _make_token(private_pem)
    with patch("app.services.keycloak.PyJWKClient") as mock_jwks:
        mock_inst = MagicMock()
        mock_key = MagicMock()
        mock_key.key = public_pem.decode()
        mock_inst.get_signing_key_from_jwt.return_value = mock_key
        mock_jwks.return_value = mock_inst
        import app.services.keycloak as kc

        kc._JWKS_CLIENT = mock_inst
        kc._JWKS_CACHED_AT = time.time()
        from app.services.keycloak import validar_token_keycloak

        res = validar_token_keycloak(token)
        assert res is not None and res["sub"] == "kc-test-sub-001"


def test_validar_token_keycloak_expirado():
    private_pem, public_pem = _gen_keypair()
    token = _make_token(private_pem, {"exp": int(time.time()) - 10})
    with patch("app.services.keycloak.PyJWKClient") as mock_jwks:
        mock_inst = MagicMock()
        mock_key = MagicMock()
        mock_key.key = public_pem.decode()
        mock_inst.get_signing_key_from_jwt.return_value = mock_key
        mock_jwks.return_value = mock_inst
        import app.services.keycloak as kc

        kc._JWKS_CLIENT = mock_inst
        kc._JWKS_CACHED_AT = time.time()
        from app.services.keycloak import validar_token_keycloak

        assert validar_token_keycloak(token) is None


def test_validar_token_keycloak_iss_errado():
    private_pem, public_pem = _gen_keypair()
    token = _make_token(private_pem, {"iss": "https://evil.example.com/realms/fake"})
    with patch("app.services.keycloak.PyJWKClient") as mock_jwks:
        mock_inst = MagicMock()
        mock_key = MagicMock()
        mock_key.key = public_pem.decode()
        mock_inst.get_signing_key_from_jwt.return_value = mock_key
        mock_jwks.return_value = mock_inst
        import app.services.keycloak as kc

        kc._JWKS_CLIENT = mock_inst
        kc._JWKS_CACHED_AT = time.time()
        from app.services.keycloak import validar_token_keycloak

        assert validar_token_keycloak(token) is None


@pytest.mark.asyncio
async def test_get_current_user_keycloak_provisiona(client):
    # client fixture cria admin e DB, mas vamos mockar um token Keycloak novo
    private_pem, public_pem = _gen_keypair()
    sub = f"kc-provision-{uuid.uuid4().hex[:8]}"
    email = f"{sub}@test.com"
    token = _make_token(private_pem, {"sub": sub, "email": email, "realm_access": {"roles": ["participante"]}})
    with patch("app.services.keycloak.PyJWKClient") as mock_jwks:
        mock_inst = MagicMock()
        mock_key = MagicMock()
        mock_key.key = public_pem.decode()
        mock_inst.get_signing_key_from_jwt.return_value = mock_key
        mock_jwks.return_value = mock_inst
        import app.services.keycloak as kc

        kc._JWKS_CLIENT = mock_inst
        kc._JWKS_CACHED_AT = time.time()
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.api.deps import get_current_user
        from app.database import engine

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            with patch(
                "app.api.deps.validar_token_keycloak",
                return_value={
                    "sub": sub,
                    "email": email,
                    "name": email,
                    "iss": settings.KEYCLOAK_ISSUER,
                    "aud": settings.KEYCLOAK_CLIENT_ID,
                    "exp": int(time.time()) + 300,
                    "realm_access": {"roles": ["participante"]},
                    "resource_access": {settings.KEYCLOAK_CLIENT_ID: {"roles": ["participante"]}},
                },
            ):
                user = await get_current_user(token=token, db=db)
                assert user.email == email
                assert user.keycloak_sub == sub
                assert user.auth_provider == "keycloak"


@pytest.mark.asyncio
async def test_get_current_user_keycloak_participante_pendente(client):
    """Participante do Keycloak nasce pendente + cria solicitacao (quando flag off).

    Comportamento reversivel: KEYCLOAK_PARTICIPANTE_APROVADO=True (padrao) nasce
    aprovado; este teste usa False para validar o fluxo antigo (pendente).
    """
    private_pem, public_pem = _gen_keypair()
    sub = f"kc-pend-test-{uuid.uuid4().hex[:8]}"
    email = f"{sub}@test.com"
    token = _make_token(
        private_pem, {"sub": sub, "email": email, "resource_access": {"treinamento-front": {"roles": ["participante"]}}}
    )
    with patch("app.services.keycloak.PyJWKClient") as mock_jwks:
        mock_inst = MagicMock()
        mock_key = MagicMock()
        mock_key.key = public_pem.decode()
        mock_inst.get_signing_key_from_jwt.return_value = mock_key
        mock_jwks.return_value = mock_inst
        import app.services.keycloak as kc

        kc._JWKS_CLIENT = mock_inst
        kc._JWKS_CACHED_AT = time.time()
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.api.deps import get_current_user
        from app.database import engine
        from app.models.credenciamento import SolicitacaoCredenciamento

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            with patch("app.api.deps.settings.KEYCLOAK_PARTICIPANTE_APROVADO", False), patch(
                "app.api.deps.validar_token_keycloak",
                return_value={
                    "sub": sub,
                    "email": email,
                    "name": email,
                    "iss": settings.KEYCLOAK_ISSUER,
                    "aud": settings.KEYCLOAK_CLIENT_ID,
                    "exp": int(time.time()) + 300,
                    "resource_access": {"treinamento-front": {"roles": ["participante"]}},
                },
            ):
                user = await get_current_user(token=token, db=db)
                assert user.email == email
                assert user.keycloak_sub == sub
                assert user.auth_provider == "keycloak"
                assert user.status_credenciamento == "pendente"
                assert user.ativo is False
                # A solicitacao precisa existir para o admin aprovar na telinha
                r = await db.execute(
                    select(SolicitacaoCredenciamento).where(SolicitacaoCredenciamento.usuario_id == user.id)
                )
                solicitacao = r.scalar_one_or_none()
                assert solicitacao is not None, "solicitacao deveria ter sido criada"
                assert solicitacao.status == "pendente"


async def test_get_current_user_keycloak_participante_aprovado_padrao(client):
    """Participante do Keycloak nasce APROVADO por padrao (KEYCLOAK_PARTICIPANTE_APROVADO=True).

    Sem solicitacao de credenciamento — entra direto (comportamento original).
    """
    private_pem, public_pem = _gen_keypair()
    sub = f"kc-aprov-test-{uuid.uuid4().hex[:8]}"
    email = f"{sub}@test.com"
    token = _make_token(
        private_pem, {"sub": sub, "email": email, "resource_access": {"treinamento-front": {"roles": ["participante"]}}}
    )
    with patch("app.services.keycloak.PyJWKClient") as mock_jwks:
        mock_inst = MagicMock()
        mock_key = MagicMock()
        mock_key.key = public_pem.decode()
        mock_inst.get_signing_key_from_jwt.return_value = mock_key
        mock_jwks.return_value = mock_inst
        import app.services.keycloak as kc

        kc._JWKS_CLIENT = mock_inst
        kc._JWKS_CACHED_AT = time.time()
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.api.deps import get_current_user
        from app.database import engine
        from app.models.credenciamento import SolicitacaoCredenciamento

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            with patch(
                "app.api.deps.validar_token_keycloak",
                return_value={
                    "sub": sub,
                    "email": email,
                    "name": email,
                    "iss": settings.KEYCLOAK_ISSUER,
                    "aud": settings.KEYCLOAK_CLIENT_ID,
                    "exp": int(time.time()) + 300,
                    "resource_access": {"treinamento-front": {"roles": ["participante"]}},
                },
            ):
                user = await get_current_user(token=token, db=db)
                assert user.email == email
                assert user.status_credenciamento == "aprovado"
                assert user.ativo is True
                # Nao deve criar solicitacao (entra aprovado direto)
                r = await db.execute(
                    select(SolicitacaoCredenciamento).where(SolicitacaoCredenciamento.usuario_id == user.id)
                )
                assert r.scalar_one_or_none() is None, "nao deveria criar solicitacao"


def test_mapear_perfil_lms_tre_roles():
    """Roles do IDESP (TRE_*) mapeiam para o perfil LMS de maior hierarquia."""
    from app.services.keycloak import mapear_perfil_lms

    casos = {
        "TRE_ADM": "administrador_geral",
        "TRE_AUDITOR": "auditor",
        "TRE_GESTOR": "gestor",
        "TRE_INSTRUTOR": "instrutor",
        "TRE_OPERADOR": "administrador",
        "TRE_PARTICIPANTE": "participante",
        # nomes antigos continuam valendo (compatibilidade retroativa)
        "administrador_geral": "administrador_geral",
        "instrutor": "instrutor",
    }
    for role, esperado in casos.items():
        assert mapear_perfil_lms([role]) == esperado, f"{role} -> {esperado}"


def test_mapear_perfil_lms_prioridade_e_fallback():
    """Varias roles: o perfil mais alto vence. Role desconhecida -> participante."""
    from app.services.keycloak import mapear_perfil_lms

    assert mapear_perfil_lms(["TRE_GESTOR", "TRE_INSTRUTOR"]) == "instrutor"
    assert mapear_perfil_lms(["TRE_PARTICIPANTE", "TRE_ADM"]) == "administrador_geral"
    assert mapear_perfil_lms(["ROLE_DESCONHECIDA"]) == "participante"
    assert mapear_perfil_lms([]) == "participante"


@pytest.mark.asyncio
async def test_get_current_user_keycloak_gestao_aprovado(client):
    """Perfil de gestao (role do IDESP) nasce aprovado direto."""
    private_pem, public_pem = _gen_keypair()
    sub = f"kc-gestao-test-{uuid.uuid4().hex[:8]}"
    email = f"{sub}@test.com"
    token = _make_token(
        private_pem,
        {"sub": sub, "email": email, "resource_access": {"treinamento-front": {"roles": ["administrador_geral"]}}},
    )
    with patch("app.services.keycloak.PyJWKClient") as mock_jwks:
        mock_inst = MagicMock()
        mock_key = MagicMock()
        mock_key.key = public_pem.decode()
        mock_inst.get_signing_key_from_jwt.return_value = mock_key
        mock_jwks.return_value = mock_inst
        import app.services.keycloak as kc

        kc._JWKS_CLIENT = mock_inst
        kc._JWKS_CACHED_AT = time.time()
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.api.deps import get_current_user
        from app.database import engine

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            with patch(
                "app.api.deps.validar_token_keycloak",
                return_value={
                    "sub": sub,
                    "email": email,
                    "name": email,
                    "iss": settings.KEYCLOAK_ISSUER,
                    "aud": settings.KEYCLOAK_CLIENT_ID,
                    "exp": int(time.time()) + 300,
                    "resource_access": {"treinamento-front": {"roles": ["administrador_geral"]}},
                },
            ):
                user = await get_current_user(token=token, db=db)
                assert user.email == email
                assert user.status_credenciamento == "aprovado"
                assert user.ativo is True
                assert [p.perfil.nome for p in user.perfis] == ["administrador_geral"]
