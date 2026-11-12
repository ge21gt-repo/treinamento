"""Issue #116 — criar usuario.

O perfil agora e criado no Keycloak (role + e-mail de acao) e a plataforma nao
guarda senha. Cobre a matriz de "quem cria quem", os 403, a falha do Keycloak
(502 sem linha local) e a compensacao quando a gravacao local falha.
"""

import uuid

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import usuarios as usuarios_module
from app.config import settings
from app.main import app
from app.models.usuario import Usuario, UsuarioPerfil
from app.services.auth import create_access_token
from app.services.rbac import can_create_perfil

_CRIAR = "/api/v1/usuarios/criar-subordinado"


class TestMatrizDeCriacao:
    @pytest.mark.parametrize(
        "criador,alvo,esperado",
        [
            ("administrador_geral", "administrador_geral", True),
            ("administrador_geral", "auditor", True),
            ("administrador", "administrador", True),
            ("administrador", "auditor", False),
            ("gestor", "instrutor", True),
            ("gestor", "participante", True),
            ("gestor", "gestor", False),
            ("instrutor", "participante", False),
            ("auditor", "participante", False),
            ("participante", "participante", False),
            ("desconhecido", "participante", False),
        ],
    )
    def test_matriz(self, criador, alvo, esperado):
        assert can_create_perfil(criador, alvo) is esperado


async def _criar_usuario_local(perfil_nome: str) -> tuple[uuid.UUID, str]:
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    usuario_id = uuid.uuid4()
    email = f"{perfil_nome}.{usuario_id.hex[:8]}@test.com"
    try:
        async with maker() as sessao:
            perfil_id = (
                await sessao.execute(
                    text("SELECT id FROM lms.perfis WHERE nome = :n"), {"n": perfil_nome}
                )
            ).scalar_one()
            sessao.add(
                Usuario(
                    id=usuario_id,
                    nome_completo=perfil_nome,
                    email=email,
                    senha_hash=None,
                    ativo=True,
                    status_credenciamento="aprovado",
                    aceite_lgpd=True,
                )
            )
            await sessao.flush()
            sessao.add(UsuarioPerfil(usuario_id=usuario_id, perfil_id=perfil_id))
            await sessao.commit()
    finally:
        await engine.dispose()
    return usuario_id, email


async def _linha(email: str):
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as sessao:
            return (
                await sessao.execute(select(Usuario).where(Usuario.email == email))
            ).scalar_one_or_none()
    finally:
        await engine.dispose()


def _cliente(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


def _token(usuario_id: uuid.UUID, email: str) -> str:
    return create_access_token(data={"sub": str(usuario_id), "email": email})


async def test_admin_geral_cria_participante_sem_senha(db_clean, admin_token, keycloak_admin_fake):
    async with _cliente(admin_token) as ac:
        r = await ac.post(
            _CRIAR,
            json={
                "nome_completo": "Novo Participante",
                "email": "novo116@test.com",
                "perfil": "participante",
            },
        )

    assert r.status_code == status.HTTP_201_CREATED, r.text
    assert "participante" in r.json()["perfis"]
    assert keycloak_admin_fake["criados"] == [("novo116@test.com", "Novo Participante")]
    assert keycloak_admin_fake["roles"] == [("kc-1", "participante")]
    assert keycloak_admin_fake["emails"] == ["kc-1"]

    linha = await _linha("novo116@test.com")
    assert linha is not None
    assert linha.senha_hash is None
    assert linha.keycloak_sub == "kc-1"
    assert linha.auth_provider == "keycloak"


async def test_administrador_nao_cria_auditor(db_clean, keycloak_admin_fake):
    usuario_id, email = await _criar_usuario_local("administrador")
    async with _cliente(_token(usuario_id, email)) as ac:
        r = await ac.post(
            _CRIAR,
            json={
                "nome_completo": "Auditor Novo",
                "email": "auditor116@test.com",
                "perfil": "auditor",
            },
        )

    assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
    assert keycloak_admin_fake["criados"] == []
    assert await _linha("auditor116@test.com") is None


async def test_gestor_cria_instrutor_mas_nao_gestor(db_clean, keycloak_admin_fake):
    usuario_id, email = await _criar_usuario_local("gestor")
    token = _token(usuario_id, email)

    async with _cliente(token) as ac:
        negado = await ac.post(
            _CRIAR,
            json={"nome_completo": "Gestor Novo", "email": "gestor116@test.com", "perfil": "gestor"},
        )
        permitido = await ac.post(
            _CRIAR,
            json={
                "nome_completo": "Instrutor Novo",
                "email": "instrutor116@test.com",
                "perfil": "instrutor",
            },
        )

    assert negado.status_code == status.HTTP_403_FORBIDDEN, negado.text
    assert permitido.status_code == status.HTTP_201_CREATED, permitido.text
    assert keycloak_admin_fake["roles"] == [("kc-1", "instrutor")]


async def test_falha_do_keycloak_responde_502_e_nao_cria_local(db_clean, admin_token, monkeypatch):
    from app.services import keycloak_admin as ka

    async def falha(*args, **kwargs):
        raise ka.KeycloakAdminError("indisponivel")

    monkeypatch.setattr(ka, "criar_usuario", falha)

    async with _cliente(admin_token) as ac:
        r = await ac.post(
            _CRIAR,
            json={
                "nome_completo": "Falha KC",
                "email": "falhakeycloak116@test.com",
                "perfil": "participante",
            },
        )

    assert r.status_code == status.HTTP_502_BAD_GATEWAY, r.text
    assert await _linha("falhakeycloak116@test.com") is None


async def test_falha_local_remove_o_usuario_do_keycloak(
    db_clean, admin_token, keycloak_admin_fake, monkeypatch
):
    def explode(**kwargs):
        raise RuntimeError("falha na gravacao local")

    monkeypatch.setattr(usuarios_module, "SolicitacaoCredenciamento", explode)

    async with _cliente(admin_token) as ac:
        with pytest.raises(RuntimeError):
            await ac.post(
                _CRIAR,
                json={
                    "nome_completo": "Compensa",
                    "email": "compensa116@test.com",
                    "perfil": "participante",
                },
            )

    assert keycloak_admin_fake["removidos"] == ["kc-1"]
    assert await _linha("compensa116@test.com") is None
