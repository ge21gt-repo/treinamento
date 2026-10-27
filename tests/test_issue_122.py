"""Issue #122: o token do Keycloak era aceito de qualquer client do realm.

`validar_token_keycloak` conferia assinatura, `iss` e `exp`, mas passava
`verify_aud: False` e deixava a checagem de audiencia COMENTADA logo abaixo do
decode. O docstring dela chegava a dizer que conferia `aud (treinamento-front)`.
Na pratica, qualquer token valido do `idesp-realm`, emitido para qualquer
client, entrava como se fosse da plataforma.

O client a exigir nao precisava de ninguem: ja estava configurado como
`KEYCLOAK_CLIENT_ID` (`treinamento-front`), no manifesto do cluster e no .env.

Os testes de audiencia nao tocam o banco - sao chamadas diretas a funcao, com
o JWKS trocado por um par de chaves gerado aqui.
"""

import os
import time
import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.services.keycloak import audiencia_confere, clientes_aceitos, validar_token_keycloak

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]


def _request_falso(caminho="/api/v1/usuarios/me"):
    """Request minimo: get_current_user recebe um desde a issue #119."""
    from starlette.requests import Request

    return Request(
        {"type": "http", "method": "GET", "path": caminho, "headers": [], "query_string": b""}
    )


def _gen_keypair():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    publica = chave.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return privada, publica


def _token(privada, **alteracoes):
    payload = {
        "iss": settings.KEYCLOAK_ISSUER,
        "aud": settings.KEYCLOAK_CLIENT_ID,
        "sub": "kc-122-sub",
        "email": "kc122@test.com",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
        "resource_access": {settings.KEYCLOAK_CLIENT_ID: {"roles": ["participante"]}},
    }
    payload.update(alteracoes)
    return jwt.encode(payload, privada, algorithm="RS256", headers={"kid": "test-kid"})


class _JwksFalso:
    """Troca o PyJWKClient pela chave publica gerada no teste."""

    def __init__(self, publica):
        self.publica = publica

    def __enter__(self):
        self.patcher = patch("app.services.keycloak.PyJWKClient")
        mock_cls = self.patcher.start()
        inst = MagicMock()
        chave = MagicMock()
        chave.key = self.publica.decode()
        inst.get_signing_key_from_jwt.return_value = chave
        mock_cls.return_value = inst

        import app.services.keycloak as kc

        self.kc = kc
        self.antes = (kc._JWKS_CLIENT, kc._JWKS_CACHED_AT)
        kc._JWKS_CLIENT = inst
        kc._JWKS_CACHED_AT = time.time()
        return self

    def __exit__(self, *exc):
        self.kc._JWKS_CLIENT, self.kc._JWKS_CACHED_AT = self.antes
        self.patcher.stop()
        return False


class TestIssue122Audiencia:
    """O critério de aceite: outro client é recusado, o da plataforma passa."""

    def test_token_do_client_da_plataforma_e_aceito(self):
        privada, publica = _gen_keypair()
        with _JwksFalso(publica):
            assert validar_token_keycloak(_token(privada)) is not None

    def test_token_de_outro_client_do_realm_e_recusado(self):
        """O buraco da issue: assinatura boa, issuer certo, client alheio.

        `aud: account` e `azp` de outro sistema e exatamente a forma de um
        token de Direct Access de outro client do mesmo realm.
        """
        privada, publica = _gen_keypair()
        token = _token(privada, aud="account", azp="outro-sistema")
        with _JwksFalso(publica):
            assert validar_token_keycloak(token) is None

    def test_token_sem_aud_nem_azp_e_recusado(self):
        privada, publica = _gen_keypair()
        payload = {
            "iss": settings.KEYCLOAK_ISSUER,
            "sub": "x",
            "exp": int(time.time()) + 300,
        }
        token = jwt.encode(payload, privada, algorithm="RS256", headers={"kid": "test-kid"})
        with _JwksFalso(publica):
            assert validar_token_keycloak(token) is None

    def test_client_de_teste_recusado_por_default_e_aceito_quando_liberado(self, monkeypatch):
        """A exceção do `treinamento-testes` sai de produção e vira configuração.

        Era a justificativa de a audiência estar desligada. Agora é uma
        setting, vazia por default.
        """
        privada, publica = _gen_keypair()
        token = _token(privada, aud="account", azp="treinamento-testes")

        with _JwksFalso(publica):
            assert validar_token_keycloak(token) is None

            monkeypatch.setattr(settings, "KEYCLOAK_CLIENTS_EXTRA", "treinamento-testes")
            assert validar_token_keycloak(token) is not None

    def test_aud_em_lista_com_o_client_e_aceito(self):
        """O Keycloak manda `aud` como lista quando há mais de uma audiência."""
        privada, publica = _gen_keypair()
        token = _token(privada, aud=["account", settings.KEYCLOAK_CLIENT_ID])
        with _JwksFalso(publica):
            assert validar_token_keycloak(token) is not None

    def test_assinatura_invalida_continua_recusada(self):
        """Não regride: a audiência certa não substitui a assinatura."""
        privada, _ = _gen_keypair()
        _, outra_publica = _gen_keypair()
        with _JwksFalso(outra_publica):
            assert validar_token_keycloak(_token(privada)) is None


class TestIssue122FuncaoDaAudiencia:
    """A regra em si, sem JWT no meio."""

    def test_clientes_aceitos_so_o_da_plataforma_por_default(self, monkeypatch):
        monkeypatch.setattr(settings, "KEYCLOAK_CLIENTS_EXTRA", "")
        assert clientes_aceitos() == {settings.KEYCLOAK_CLIENT_ID}

    def test_clientes_extra_aceita_lista_com_espaco(self, monkeypatch):
        monkeypatch.setattr(settings, "KEYCLOAK_CLIENTS_EXTRA", " treinamento-testes , outro ")
        assert clientes_aceitos() == {settings.KEYCLOAK_CLIENT_ID, "treinamento-testes", "outro"}

    def test_confere_aud_e_azp(self):
        cliente = settings.KEYCLOAK_CLIENT_ID
        assert audiencia_confere({"aud": cliente}) is True
        assert audiencia_confere({"aud": ["account", cliente]}) is True
        assert audiencia_confere({"azp": cliente}) is True
        assert audiencia_confere({"aud": "account", "azp": "alheio"}) is False
        assert audiencia_confere({}) is False


async def _criar_usuario_local(email):
    """Usuario local, sem keycloak_sub: o caso do vinculo por e-mail."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.usuario import Usuario

    eng = create_async_engine(_URL)
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessao:
            user = Usuario(
                nome_completo="Alvo do vinculo",
                email=email,
                senha_hash="x",
                ativo=True,
                status_credenciamento="aprovado",
                auth_provider="local",
            )
            sessao.add(user)
            await sessao.commit()
            return user.id
    finally:
        await eng.dispose()


async def _tentar_vincular(email, claims):
    """Chama get_current_user com um payload de Keycloak controlado.

    Devolve o usuario, ou None quando a dependencia recusa com 401.
    """
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.api.deps import get_current_user

    payload = {
        "sub": f"kc-122-{uuid.uuid4().hex[:8]}",
        "email": email,
        "iss": settings.KEYCLOAK_ISSUER,
        "aud": settings.KEYCLOAK_CLIENT_ID,
        "exp": int(time.time()) + 300,
        "resource_access": {settings.KEYCLOAK_CLIENT_ID: {"roles": ["participante"]}},
    }
    payload.update(claims)

    eng = create_async_engine(_URL)
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:
            with patch("app.api.deps.validar_token_keycloak", return_value=payload):
                try:
                    return await get_current_user(_request_falso(), token="qualquer", db=db)
                except HTTPException:
                    return None
    finally:
        await eng.dispose()


@pytest.mark.asyncio
class TestIssue122EmailVerificado:
    """Item 2: o vínculo por e-mail exige `email_verified`.

    Sem isso, quem conseguisse um token do realm declarando o e-mail de outra
    pessoa assumia a conta dela — e os perfis dela.
    """

    async def test_com_email_verificado_vincula(self, client):
        email = f"vinc-ok-{uuid.uuid4().hex[:8]}@test.com"
        await _criar_usuario_local(email)

        user = await _tentar_vincular(email, {"email_verified": True})
        assert user is not None, "deveria vincular com email_verified true"
        assert user.email == email
        assert user.auth_provider == "keycloak"

    async def test_sem_a_claim_nao_vincula(self, client):
        """Claim ausente conta como não verificada - é o caso mais comum."""
        email = f"vinc-sem-{uuid.uuid4().hex[:8]}@test.com"
        await _criar_usuario_local(email)

        assert await _tentar_vincular(email, {}) is None

    async def test_com_email_verified_falso_nao_vincula(self, client):
        email = f"vinc-falso-{uuid.uuid4().hex[:8]}@test.com"
        await _criar_usuario_local(email)

        assert await _tentar_vincular(email, {"email_verified": False}) is None

    async def test_email_verified_que_nao_e_booleano_nao_vincula(self, client):
        """`is True` e deliberado: a string "true" nao serve."""
        email = f"vinc-str-{uuid.uuid4().hex[:8]}@test.com"
        await _criar_usuario_local(email)

        assert await _tentar_vincular(email, {"email_verified": "true"}) is None

    async def test_a_exigencia_pode_ser_desligada(self, client, monkeypatch):
        """Saída de emergência, para o caso de o realm não preencher a claim."""
        email = f"vinc-off-{uuid.uuid4().hex[:8]}@test.com"
        await _criar_usuario_local(email)
        monkeypatch.setattr(settings, "KEYCLOAK_EXIGIR_EMAIL_VERIFICADO", False)

        user = await _tentar_vincular(email, {})
        assert user is not None
        assert user.email == email


class TestIssue122LimiteDeTaxa:
    """Item 3: limite de taxa nas rotas de administração de usuário.

    Teste estrutural, e não uma rajada de 31 chamadas, de proposito: a chave do
    limite e o IP, e o CI roda a suite toda num processo so. Uma rajada
    esgotaria o balde e faria qualquer teste seguinte que editasse usuario
    receber 429 - um teste que quebra outros.
    """

    def test_as_rotas_administrativas_estao_limitadas(self):
        from app.api.rate_limit import limiter
        from app.main import app  # noqa: F401  (registra as rotas no limiter)

        esperadas = {
            "app.api.usuarios.criar_subordinado",
            "app.api.usuarios.atualizar_usuario",
            "app.api.usuarios.excluir_usuario",
            "app.api.usuarios.atribuir_perfil",
        }
        registradas = set(limiter._route_limits)
        faltando = esperadas - registradas
        assert not faltando, f"rotas sem limite de taxa: {sorted(faltando)}"

        for nome in sorted(esperadas):
            limites = [str(limite.limit) for limite in limiter._route_limits[nome]]
            assert limites == ["30 per 1 minute"], (nome, limites)
