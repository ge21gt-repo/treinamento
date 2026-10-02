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


async def _entrar(sub, email, roles, outros=None):
    """Helper do dev (issue #95): chama get_current_user com token mockado."""
    recursos = {"treinamento-front": {"roles": roles}, **(outros or {})}
    payload = {"sub": sub, "email": email, "name": email,
               "exp": int(time.time()) + 300, "resource_access": recursos}
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.api.deps import get_current_user
    from app.database import engine
    from app.schemas.usuario import UsuarioRead

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        with patch("app.api.deps.validar_token_keycloak", return_value=payload):
            user = await get_current_user(token="x", db=db)
            return sorted(UsuarioRead.model_validate(user).perfis)


async def _criar_usuario_local_participante() -> str:
    """Cria um usuario local so participante (sem keycloak_sub), retorna o email."""
    import uuid

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.database import engine
    from app.models.usuario import Perfil, Usuario, UsuarioPerfil

    maker = async_sessionmaker(engine, expire_on_commit=False)
    email = f"local-{uuid.uuid4().hex[:8]}@test.com"
    async with maker() as db:
        user = Usuario(email=email, nome_completo="Local", senha_hash="x",
                       ativo=True, status_credenciamento="aprovado", auth_provider="local")
        db.add(user)
        await db.flush()
        p = (await db.execute(select(Perfil).where(Perfil.nome == "participante"))).scalar_one()
        db.add(UsuarioPerfil(usuario_id=user.id, perfil_id=p.id))
        await db.commit()
    return email


@pytest.mark.asyncio
async def test_todas_as_roles_viram_perfil(db_clean):
    """Issue #95 ponto 1: todas as roles viram perfil (participante NAO descartado)."""
    sub = f"kc-{uuid.uuid4().hex[:10]}"
    assert await _entrar(sub, f"{sub}@t.sp.gov.br", ["TRE_PARTICIPANTE", "TRE_ADM"]) == [
        "administrador_geral", "participante"]
    sub = f"kc-{uuid.uuid4().hex[:10]}"
    assert await _entrar(sub, f"{sub}@t.sp.gov.br", ["TRE_ADM", "TRE_PARTICIPANTE", "TRE_GESTOR", "TRE_INSTRUTOR"]) == [
        "administrador_geral", "gestor", "instrutor", "participante"]


@pytest.mark.asyncio
async def test_role_de_outro_client_nao_da_perfil(db_clean):
    """Issue #95 ponto 2: role de outro client nao vira perfil."""
    sub = f"kc-{uuid.uuid4().hex[:10]}"
    perfis = await _entrar(sub, f"{sub}@t.sp.gov.br", ["TRE_PARTICIPANTE"],
                           outros={"outro-sistema": {"roles": ["gestor"]}})
    assert perfis == ["participante"]


@pytest.mark.asyncio
async def test_vinculo_por_email_ja_traz_os_perfis_novos(db_clean):
    """Issue #95 ponto 4: vinculo por email ja traz os perfis novos na 1a req."""
    email = await _criar_usuario_local_participante()
    sub = f"kc-{uuid.uuid4().hex[:10]}"
    assert await _entrar(sub, email, ["TRE_GESTOR", "TRE_PARTICIPANTE"]) == ["gestor", "participante"]


@pytest.mark.asyncio
async def test_requisicoes_paralelas_depois_da_promocao(db_clean):
    """Issue #95 ponto 3: requisicoes paralelas apos promocao nao estouram IntegrityError."""
    import asyncio

    falhas = []
    for _ in range(12):
        sub = f"kc-{uuid.uuid4().hex[:10]}"
        email = f"{sub}@t.sp.gov.br"
        await _entrar(sub, email, ["TRE_PARTICIPANTE"])
        res = await asyncio.gather(
            *[_entrar(sub, email, ["TRE_GESTOR", "TRE_INSTRUTOR", "TRE_PARTICIPANTE"]) for _ in range(16)],
            return_exceptions=True)
        falhas += [type(r).__name__ for r in res if isinstance(r, Exception)]
    assert not falhas
